import hashlib
import hmac
import io
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
import zipfile
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

import click
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import event, false, func, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from werkzeug.exceptions import SecurityError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from config import get_config, validate_production_config
from models import (
    COMMENT_CONTENT_MAX,
    COMMENT_NAME_MAX,
    COMMENT_STATUSES,
    DIFFICULTIES,
    INGREDIENT_UNITS,
    PAN_SHAPES,
    RECIPE_STATUSES,
    BLOG_IMAGE_PREFIX,
    BlogPost,
    Comment,
    DailyView,
    Recipe,
    RecipeRating,
    Tag,
    User,
    db,
    fold_search_text,
    recipe_tags,
    render_blog_markdown,
)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Zaloguj się, aby uzyskać dostęp do tej strony."
login_manager.session_protection = "basic"
csrf = CSRFProtect()
migrate = Migrate()

# Fikcyjny hash używany, gdy podany login nie istnieje - dzięki temu czas odpowiedzi
# nie zdradza, czy konto istnieje (bez tego brak sprawdzania hasła byłby wyraźnie szybszy).
_DUMMY_PASSWORD_HASH = generate_password_hash("nieistniejace-konto-atrapa")

# Hasła, które odrzucamy niezależnie od długości.
WEAK_PASSWORDS = {"zmien-to-haslo", "password", "haslo12345", "1234567890", "qwertyuiop"}

# Formaty obrazów, które potrafimy bezpiecznie zdekodować i ponownie zapisać przez Pillow.
# Mapowanie: format wykryty przez Pillow -> rozszerzenie pliku zapisywanego na dysku.
# MPO to JPEG z dodatkowymi obrazami (tak zapisują zdjęcia niektóre telefony) - zapisujemy pierwszy.
SAFE_IMAGE_FORMATS = {"JPEG": "jpg", "MPO": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


def animation_save_options(image) -> dict:
    """Opcje zapisu animacji: Pillow nie przenosi sam czasu klatek ani sposobu ich czyszczenia
    (bez niego w przezroczystym GIF-ie klatki nakładają się na siebie)."""
    durations, disposals = [], []
    for index in range(image.n_frames):
        image.seek(index)
        image.load()
        durations.append(image.info.get("duration", 100))
        disposals.append(getattr(image, "disposal_method", 0))
    image.seek(0)
    options = {"save_all": True, "duration": durations}
    if image.format == "GIF":
        options["disposal"] = disposals
    if "loop" in image.info:
        options["loop"] = image.info["loop"]
    return options


def slugify(text: str) -> str:
    """Zamienia tytuł przepisu na URL-owy 'slug', np. 'Żurek Śląski' -> 'zurek-slaski'."""
    # "ł" nie rozkłada się w NFKD na literę i znak diakrytyczny, więc inaczej by przepadło.
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)


def needs_new_slug(item, new_title: str) -> bool:
    """Slug zmienia się tylko razem z tytułem: zapis bez zmiany tytułu nie może zepsuć adresu."""
    return not item.slug or slugify(item.title or "") != slugify(new_title)


MAX_BACKUP_COUNT = 2**63 - 1  # największa liczba całkowita, którą przyjmie baza


def form_count(value: str):
    """Nieujemna liczba całkowita z pola formularza albo None. Sam str.isdigit() nie wystarcza:
    przepuszcza np. "²", którego nie da się zamienić na int, a liczba musi też zmieścić się w bazie."""
    value = value.strip()
    return int(value) if value.isascii() and value.isdigit() and len(value) <= 18 else None


def _clean_line_field(value) -> str:
    """Usuwa znaki, które zepsułyby zapis składników linia-po-linii ("|" i nowe linie)."""
    return re.sub(r"[|\r\n]+", " ", str(value if value is not None else "")).strip()


def is_negative_text(value) -> bool:
    """True dla tekstu zaczynającego się od minusa - także "-0" czy "-nan", których
    float() nie uzna za liczbę ujemną, oraz typograficznych odmian minusa."""
    return str(value if value is not None else "").strip().startswith(("-", "\u2212", "\u2013"))


def _clean_number_field(value) -> str:
    """Pole liczbowe składnika gotowe do zapisu; wartość ujemną zamienia na brak danych."""
    return "" if is_negative_text(value) else _clean_line_field(value)


def serialize_ingredient_entries(entries) -> str:
    """
    Zamienia listę wpisów [{"type": "section", "name": ...}, {"type": "item", "amount": ...,
    "unit": ..., "name": ...}] na tekst zapisywany w Recipe.ingredients. Jedno miejsce dla
    formularza i importu kopii zapasowej - dzięki temu dane z obu źródeł są tak samo czyszczone.
    """
    lines = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        if kind == "section":
            name = _clean_line_field(entry.get("name"))[:80]
            lines.append(f"{Recipe.SECTION_MARKER}{name}")
        elif kind == "item":
            name = _clean_line_field(entry.get("name"))
            if not name:
                continue
            # amount jest pierwszym polem linii - nie może przypadkiem wyglądać jak nagłówek sekcji
            amount = _clean_number_field(entry.get("amount")).replace(Recipe.SECTION_MARKER, "")
            unit = _clean_line_field(entry.get("unit"))
            kcal = _clean_number_field(entry.get("kcal"))
            protein = _clean_number_field(entry.get("protein"))
            fat = _clean_number_field(entry.get("fat"))
            carbs = _clean_number_field(entry.get("carbs"))
            lines.append(f"{amount}|{unit}|{kcal}|{protein}|{fat}|{carbs}|{name}")
    return "\n".join(lines)


def is_safe_redirect_target(target) -> bool:
    """True tylko dla ścieżek WEWNĄTRZ tej witryny (ochrona przed open redirect w ?next=)."""
    if not target or not isinstance(target, str):
        return False
    if any(ch in target for ch in "\r\n\t\\"):
        return False
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/") and not target.startswith("//")


# ---------- wyszukiwanie po składnikach ----------
# Składniki, które ma prawie każdy - nie liczymy ich jako „brakujące".
# Początki słów (bez polskich znaków), żeby objąć odmianę: sól/soli, cukier/cukru, woda/wody...
PANTRY_BASICS = ("sol", "pieprz", "wod", "cukier", "cukr", "olej", "oliw")
_INGREDIENT_STOPWORDS = {"i", "oraz", "lub", "albo", "a", "z", "ze", "w", "mam", "troche", "do", "smaku"}


def _fold(text: str) -> str:
    """Małe litery bez polskich znaków: 'Mąka' -> 'maka', 'Żółtka' -> 'zoltka'."""
    text = str(text).lower().replace("ł", "l")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# Końcówki odmiany (bez polskich znaków), od najdłuższych. Rdzeń musi mieć co najmniej 3 litery.
_INGREDIENT_ENDINGS = (
    "owego", "owych", "owymi", "owej", "owym", "owy", "owa", "owe", "ami", "ach", "ego", "emu", "ych", "ymi",
    "ow", "om", "em", "ej", "ym", "ie", "ek", "a", "e", "i", "o", "u", "y",
)
# „Mąka" i „mak" po usunięciu ogonków są nieodróżnialne. Formy bez ogonków: wpisane z telefonu.
_MAKA_WORDS = {"maka", "maki", "make"}


def _stem(word: str) -> str:
    """Rdzeń polskiego słowa po obcięciu końcówki odmiany, żeby 'mleko' i 'mleka' były równe,
    a 'mąka' i 'makaron' różne. Przyjmuje słowo małymi literami, jeszcze z polskimi znakami."""
    if word.startswith("mąk") or word in _MAKA_WORDS:
        return "mąk"
    word = _fold(word)
    for ending in _INGREDIENT_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def parse_ingredient_terms(text: str):
    """'jajka, mąkę i mleko' -> [('jajka', ['jajk']), ('mąkę', ['mąk']), ('mleko', ['mlek'])]."""
    terms = []
    for chunk in re.split(r"[,;\n]+|\s+i\s+|\s+oraz\s+", text):
        words = [w for w in re.findall(r"[\w-]+", chunk.lower()) if _fold(w) not in _INGREDIENT_STOPWORDS]
        if not words:
            continue
        stems = [_stem(w) for w in words if len(w) >= 3]
        if stems:
            terms.append((chunk.strip(), stems))
    return terms[:15]


def _same_stem(first: str, second: str) -> bool:
    """Równe rdzenie albo różnica jednego zdrobniającego „k": 'jaj'/'jajk', 'cebul'/'cebulk'."""
    shorter, longer = sorted((first, second), key=len)
    return first == second or longer == shorter + "k"


def _ingredient_matches(name: str, stems) -> bool:
    name_stems = [_stem(w) for w in re.findall(r"[\w-]+", name.lower())]
    return all(any(_same_stem(found, stem) for found in name_stems) for stem in stems)


def match_recipe_ingredients(recipe, terms):
    """Porównuje składniki przepisu z listą tego, co ma użytkownik."""
    names = [item["name"] for item in recipe.ingredients_list]
    matched_terms, matched_names = [], set()
    for label, stems in terms:
        hits = [n for n in names if _ingredient_matches(n, stems)]
        if hits:
            matched_terms.append(label)
            matched_names.update(hits)
    def is_basic(name):
        words = re.findall(r"\w+", _fold(name))
        # Tylko krótkie nazwy („sól", „cukru", „oliwa z oliwek") - „cukier puder" czy
        # „sól morska" to wciąż podstawy, ale „sos sojowy" już nie (inny początek).
        return bool(words) and words[0].startswith(PANTRY_BASICS)

    countable = [n for n in names if not is_basic(n)]
    missing = [n for n in countable if n not in matched_names]
    return {
        "matched_terms": matched_terms,
        "matched": [n for n in countable if n in matched_names],
        "missing": missing,
        "total": len(countable),
    }


# Odwołania do wgranych zdjęć w adresach i treści wpisów na blogu (Markdown).
BLOG_UPLOAD_REF_RE = re.compile(r"/static/uploads/([A-Za-z0-9_-]+\.[A-Za-z0-9]+)")


def image_names_in(*texts) -> set:
    """Nazwy plików z static/uploads wskazane w podanych adresach lub treściach."""
    return {name for text in texts for name in BLOG_UPLOAD_REF_RE.findall(text or "")}

# Strony publiczne, które service worker (PWA) może zapisać do czytania offline.
OFFLINE_CACHEABLE_ENDPOINTS = {
    "index", "recipe_detail", "blog_index", "blog_detail", "shopping_list", "favorites", "offline_page",
}


def validate_new_password(password: str, min_length: int):
    """Zwraca komunikat błędu albo None, jeśli hasło jest akceptowalne."""
    if len(password or "") < min_length:
        return f"Hasło musi mieć co najmniej {min_length} znaków."
    if password.lower() in WEAK_PASSWORDS:
        return "To hasło jest zbyt popularne - wybierz inne."
    return None


def _escape_like(value: str) -> str:
    """Escapuje znaki specjalne wzorca LIKE, żeby '%' i '_' z wyszukiwarki były zwykłymi znakami."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_sqlite_pragmas_registered = False


def _register_sqlite_pragmas():
    """Włącza klucze obce, WAL i timeout blokady dla każdego połączenia SQLite (raz na proces)."""
    global _sqlite_pragmas_registered
    if _sqlite_pragmas_registered:
        return
    _sqlite_pragmas_registered = True

    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def admin_required(view_func):
    """Dekorator: dopuszcza tylko zalogowanego administratora."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)

    return wrapped


def redaktor_or_admin_required(view_func):
    """Dekorator: dopuszcza redaktorów oraz administratorów (panel redakcyjny)."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not (current_user.is_admin or current_user.is_redaktor):
            abort(403)
        return view_func(*args, **kwargs)

    return wrapped


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or get_config())
    validate_production_config(app.config)

    # Za reverse proxy (nginx/Caddy/ngrok...) - zaufaj nagłówkom X-Forwarded-* dokładnie
    # tyle razy, ile proxy stoi przed aplikacją. Przy 0 nagłówki są ignorowane.
    proxy_count = app.config["PROXY_COUNT"]
    if proxy_count > 0:
        app.wsgi_app = ProxyFix(
            # x_host=0: domenę bierzemy z nagłówka Host (nginx ustawia go na $host, który pasuje
            # do server_name). X-Forwarded-Host nginx przepuszcza od klienta bez zmian - ufanie mu
            # pozwalałoby podrobić domenę w generowanych adresach (sitemap, robots.txt).
            app.wsgi_app, x_for=proxy_count, x_proto=proxy_count, x_host=0, x_prefix=0
        )

    logging.basicConfig(
        level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app.logger.setLevel(app.config["LOG_LEVEL"])
    if app.config.get("APP_ENV") == "production" and not app.config.get("TRUSTED_HOSTS"):
        app.logger.warning(
            "TRUSTED_HOSTS nie jest ustawione - aplikacja przyjmuje dowolny nagłówek Host. "
            "Ustaw TRUSTED_HOSTS=twoja-domena.pl w .env."
        )

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        _register_sqlite_pragmas()

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # render_as_batch: wymagane dla ALTER w SQLite
    login_manager.init_app(app)
    csrf.init_app(app)

    # Limit prób logowania per adres IP (niezależnie od blokady konta w models.User).
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
    limiter.init_app(app)
    app.extensions["recipe_limiter"] = limiter
    if app.config.get("APP_ENV") == "production" and app.config["RATELIMIT_STORAGE_URI"].startswith("memory"):
        app.logger.warning(
            "RATELIMIT_STORAGE_URI=memory:// - przy kilku workerach każdy liczy limity osobno. "
            "Ustaw redis://... (patrz README)."
        )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Schemat bazy tworzą migracje (`flask db upgrade`), a nie db.create_all().

    # ---------- nagłówki bezpieczeństwa (obrona w głąb przeciw XSS/clickjackingowi) ----------
    def _csp_nonce() -> str:
        """Losowy nonce CSP, unikalny dla każdego żądania (tworzony przy pierwszym użyciu)."""
        if "csp_nonce" not in g:
            g.csp_nonce = secrets.token_urlsafe(16)
        return g.csp_nonce

    @app.context_processor
    def inject_csp_nonce():
        # W szablonach: <script nonce="{{ csp_nonce }}">
        return {"csp_nonce": _csp_nonce()}

    @app.after_request
    def remove_unused_images(response):
        """Usuwa pliki zgłoszone przez _queue_image_cleanup, do których nic już nie odsyła.
        Decyduje stan bazy po żądaniu, więc nieudany zapis niczego nie skasuje, a plik
        używany też przez inny przepis lub wpis zostaje na dysku."""
        pending = g.pop("image_cleanup", None)
        if pending:
            try:
                db.session.rollback()  # niezatwierdzone zmiany nie mogą udawać braku odwołania
                _remove_image_files(pending - _referenced_image_names())
            except Exception:  # sprzątanie nie może zepsuć odpowiedzi; zostaje flask cleanup-images
                app.logger.exception("Nie udało się usunąć nieużywanych zdjęć")
        return response

    @app.after_request
    def set_security_headers(response):
        # Przeglądarka nie będzie "zgadywać" typu pliku inaczej niż wg Content-Type -
        # istotne m.in. dla przesłanych zdjęć, żeby nigdy nie zostały wykonane jako HTML/JS.
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Blokuje osadzanie strony w <iframe> na obcej domenie (ochrona przed clickjackingiem).
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        # CSP: skrypty wykonują się TYLKO z własnej domeny albo z jawnym nonce tego żądania.
        # Wstrzyknięty przez atakującego <script> lub onclick="..." nie zadziała.
        # style-src dopuszcza 'unsafe-inline', bo szablony używają atrybutów style="..."
        # (ryzyko znacznie mniejsze niż dla skryptów).
        nonce = g.get("csp_nonce")
        script_src = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src {script_src}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "worker-src 'self'; "
            "manifest-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )

        # HSTS ma sens tylko przez HTTPS (po ProxyFix request.is_secure odzwierciedla HTTPS z proxy).
        if request.is_secure and app.config["HSTS_SECONDS"] > 0:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={app.config['HSTS_SECONDS']}; includeSubDomains"
            )

        # Strony HTML (zwłaszcza panel) nie powinny być współdzielone w cache pośredników -
        # zawierają nonce, token CSRF i dane zależne od zalogowanego użytkownika.
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "private, no-store"
            # Service worker (PWA) zapisuje do czytania offline TYLKO publiczne strony oglądane
            # przez niezalogowanych - nigdy panelu ani stron z danymi zalogowanego użytkownika.
            if (
                response.status_code == 200
                and request.method == "GET"
                and request.endpoint in OFFLINE_CACHEABLE_ENDPOINTS
                and not current_user.is_authenticated
            ):
                response.headers["X-Offline-Cacheable"] = "1"
        return response

    # ---------- loader dla Flask-Login ----------
    @login_manager.user_loader
    def load_user(session_id):
        # Format "id:znacznik" (User.get_id). Sesja jest ważna tylko, gdy znacznik zgadza się
        # z aktualnym w bazie - po zmianie hasła lub wylogowaniu stare ciasteczka nic nie dają.
        user_id, _, token = str(session_id).partition(":")
        if not user_id.isdigit() or not token:
            return None  # m.in. sesje ze starym formatem ("1") - wymagają ponownego logowania
        user = db.session.get(User, int(user_id))
        if user is None or not user.session_token or not hmac.compare_digest(user.session_token, token):
            return None
        return user

    # ---------- widoki publiczne ----------
    # Sortowanie listy przepisów (pkt: najnowsze / najlepiej oceniane / komentowane / najszybsze / A–Z).
    SORT_OPTIONS = {
        "nowe": "Najnowsze",
        "ocena": "Najlepiej oceniane",
        "popularne": "Najpopularniejsze (30 dni)",
        "komentarze": "Najczęściej komentowane",
        "czas": "Najszybsze",
        "az": "Alfabetycznie",
    }
    # Filtr „maksymalny czas przygotowania" (minuty -> etykieta).
    TIME_FILTERS = {15: "do 15 min", 30: "do 30 min", 60: "do 1 h", 120: "do 2 h"}

    @app.route("/")
    def index():
        query = request.args.get("q", "").strip()
        tag_slug = request.args.get("tag", "").strip()
        sort = request.args.get("sort", "nowe")
        if sort not in SORT_OPTIONS:
            sort = "nowe"
        max_time = request.args.get("czas", type=int)
        if max_time not in TIME_FILTERS:
            max_time = None
        difficulty = request.args.get("trudnosc", "")
        if difficulty not in DIFFICULTIES:
            difficulty = ""
        ingredients_query = request.args.get("skladniki", "").strip()

        recipes_query = Recipe.query.filter(Recipe.status == "published")
        if query:
            # Zapytanie z samych znaków łączących byłoby po normalizacji puste i pasowało do wszystkiego.
            folded_query = fold_search_text(query)
            recipes_query = recipes_query.filter(
                Recipe.title_search.like(f"%{_escape_like(folded_query)}%", escape="\\") if folded_query else false()
            )
        active_tag = None
        if tag_slug:
            active_tag = Tag.query.filter_by(slug=tag_slug).first()
            if active_tag:
                recipes_query = recipes_query.filter(Recipe.tags.contains(active_tag))
        if max_time:
            recipes_query = recipes_query.filter(Recipe.prep_time_min.isnot(None), Recipe.prep_time_min <= max_time)
        if difficulty:
            recipes_query = recipes_query.filter(Recipe.difficulty == difficulty)

        if sort == "ocena":
            ratings = (
                db.session.query(
                    RecipeRating.recipe_id.label("rid"),
                    func.avg(RecipeRating.score).label("avg"),
                    func.count(RecipeRating.id).label("cnt"),
                )
                .group_by(RecipeRating.recipe_id)
                .subquery()
            )
            recipes_query = recipes_query.outerjoin(ratings, ratings.c.rid == Recipe.id).order_by(
                ratings.c.avg.is_(None), ratings.c.avg.desc(), ratings.c.cnt.desc(), Recipe.created_at.desc()
            )
        elif sort == "popularne":
            views = (
                db.session.query(DailyView.object_id.label("rid"), func.sum(DailyView.views).label("cnt"))
                .filter(DailyView.kind == "recipe", DailyView.day >= date.today() - timedelta(days=29))
                .group_by(DailyView.object_id)
                .subquery()
            )
            recipes_query = recipes_query.outerjoin(views, views.c.rid == Recipe.id).order_by(
                func.coalesce(views.c.cnt, 0).desc(), Recipe.created_at.desc()
            )
        elif sort == "komentarze":
            comment_counts = (
                db.session.query(Comment.recipe_id.label("rid"), func.count(Comment.id).label("cnt"))
                .filter(Comment.status == "published", Comment.recipe_id.isnot(None))
                .group_by(Comment.recipe_id)
                .subquery()
            )
            recipes_query = recipes_query.outerjoin(comment_counts, comment_counts.c.rid == Recipe.id).order_by(
                func.coalesce(comment_counts.c.cnt, 0).desc(), Recipe.created_at.desc()
            )
        elif sort == "czas":
            recipes_query = recipes_query.order_by(
                Recipe.prep_time_min.is_(None), Recipe.prep_time_min.asc(), Recipe.title.asc()
            )
        elif sort == "az":
            recipes_query = recipes_query.order_by(Recipe.title.asc())
        else:
            recipes_query = recipes_query.order_by(Recipe.created_at.desc())

        recipes = recipes_query.all()

        # Wyszukiwanie po składnikach („mam jajka, mąkę i mleko"): zostają przepisy, które
        # zawierają choć jeden podany składnik; najpierw te, w których pasuje najwięcej
        # podanych składników, a przy remisie - te, którym brakuje najmniej.
        matches = {}
        if ingredients_query:
            terms = parse_ingredient_terms(ingredients_query)
            for recipe in recipes:
                match = match_recipe_ingredients(recipe, terms)
                if match["matched_terms"]:
                    matches[recipe.id] = match
            recipes = [r for r in recipes if r.id in matches]
            recipes.sort(key=lambda r: (-len(matches[r.id]["matched_terms"]), len(matches[r.id]["missing"])))

        all_tags = Tag.query.order_by(Tag.name).all()
        return render_template(
            "index.html",
            recipes=recipes,
            query=query,
            all_tags=all_tags,
            active_tag=active_tag,
            rating_stats=_rating_stats([r.id for r in recipes]),
            sort=sort,
            sort_options=SORT_OPTIONS,
            max_time=max_time,
            time_filters=TIME_FILTERS,
            difficulty=difficulty,
            difficulties=DIFFICULTIES,
            ingredients_query=ingredients_query,
            matches=matches,
        )

    @app.route("/przepis/<slug>")
    def recipe_detail(slug):
        recipe = Recipe.query.filter_by(slug=slug).first_or_404()
        if recipe.status != "published":
            # Niezatwierdzony przepis widzi tylko jego autor albo administrator.
            is_owner = current_user.is_authenticated and recipe.author_id == current_user.id
            is_admin_viewer = current_user.is_authenticated and current_user.is_admin
            if not (is_owner or is_admin_viewer):
                abort(404)
        if recipe.is_published:
            _count_view("recipe", recipe.id)
        avg, count = _rating_stats([recipe.id]).get(recipe.id, (None, 0))
        similar, similar_by_tags = _similar_recipes(recipe)
        my_rating = None
        voter_hash = _voter_hash_from_cookie()
        if voter_hash:
            my_rating = RecipeRating.query.filter_by(recipe_id=recipe.id, voter_hash=voter_hash).first()
        return render_template(
            "recipe_detail.html",
            recipe=recipe,
            rating_avg=avg,
            rating_count=count,
            my_rating=my_rating.score if my_rating else None,
            recipe_jsonld=_recipe_jsonld(recipe, avg, count) if recipe.is_published else None,
            comments=_published_comments(Comment.recipe_id == recipe.id),
            similar=similar,
            similar_by_tags=similar_by_tags,
            similar_stats=_rating_stats([r.id for r in similar]),
            **_comment_form_context(),
        )

    def _similar_recipes(recipe, limit=3):
        """Przepisy z największą liczbą wspólnych tagów. Gdy żaden nie ma wspólnego tagu -
        po prostu najnowsze (wtedy sekcja nazywa się „Inne przepisy"). Zwraca (lista, czy_po_tagach)."""
        base = Recipe.query.filter(Recipe.status == "published", Recipe.id != recipe.id)
        tag_ids = [t.id for t in recipe.tags]
        if tag_ids:
            shared = func.count(recipe_tags.c.tag_id)
            rows = (
                base.join(recipe_tags, recipe_tags.c.recipe_id == Recipe.id)
                .filter(recipe_tags.c.tag_id.in_(tag_ids))
                .group_by(Recipe.id)
                .order_by(shared.desc(), Recipe.created_at.desc())
                .limit(limit)
                .all()
            )
            if rows:
                return rows, True
        return base.order_by(Recipe.created_at.desc()).limit(limit).all(), False

    # ---------- własne statystyki wyświetleń (bez zewnętrznej analityki i ciasteczek) ----------
    _BOT_UA_RE = re.compile(r"bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests|headless", re.I)

    def _count_view(kind, object_id):
        """+1 do dzisiejszego licznika strony. Pomija zalogowanych (redakcja) i boty.
        Błąd licznika nigdy nie może zepsuć wyświetlenia przepisu."""
        if current_user.is_authenticated or _BOT_UA_RE.search(request.user_agent.string or ""):
            return
        # Prefetch/prerender przeglądarki to nie jest prawdziwe wyświetlenie.
        if request.headers.get("Purpose") == "prefetch" or request.headers.get("Sec-Purpose", "").startswith("prefetch"):
            return
        today = date.today()
        try:
            result = db.session.execute(
                update(DailyView)
                .where(DailyView.kind == kind, DailyView.object_id == object_id, DailyView.day == today)
                .values(views=DailyView.views + 1)
            )
            if result.rowcount == 0:
                db.session.add(DailyView(kind=kind, object_id=object_id, day=today, views=1))
            db.session.commit()
        except IntegrityError:
            # Równoległe pierwsze wyświetlenie dnia - wiersz już istnieje, więc tylko zwiększamy.
            db.session.rollback()
            db.session.execute(
                update(DailyView)
                .where(DailyView.kind == kind, DailyView.object_id == object_id, DailyView.day == today)
                .values(views=DailyView.views + 1)
            )
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            app.logger.exception("Nie udało się zapisać wyświetlenia")

    # ---------- dane strukturalne dla wyszukiwarek (schema.org/Recipe jako JSON-LD) ----------
    def _recipe_jsonld(recipe, rating_avg, rating_count):
        """Opis przepisu w formacie rozumianym przez Google (karta z gwiazdkami, czasem, kcal)."""
        def ingredient_text(item):
            return " ".join(p for p in (item["amount"], item["unit"], item["name"]) if p)

        data = {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": recipe.title,
            "url": url_for("recipe_detail", slug=recipe.slug, _external=True),
            "recipeIngredient": [ingredient_text(i) for i in recipe.ingredients_list],
            "recipeInstructions": [
                {"@type": "HowToStep", "position": n, "text": step}
                for n, step in enumerate(recipe.instructions_list, start=1)
            ],
        }
        if recipe.description:
            data["description"] = recipe.description
        if recipe.image_url:
            data["image"] = [request.host_url.rstrip("/") + recipe.image_url]
        if recipe.author:
            data["author"] = {"@type": "Person", "name": recipe.author.username}
        if recipe.created_at:
            data["datePublished"] = recipe.created_at.date().isoformat()
        if recipe.servings:
            data["recipeYield"] = f"{recipe.servings} porcji"
        if recipe.prep_time_min:
            data["totalTime"] = f"PT{recipe.prep_time_min}M"
        if recipe.tags:
            data["keywords"] = ", ".join(t.name for t in recipe.tags)
            data["recipeCategory"] = recipe.tags[0].name
        per_serving = recipe.nutrition_per_serving
        if per_serving:
            data["nutrition"] = {
                "@type": "NutritionInformation",
                "calories": f"{round(per_serving['kcal'])} kcal",
                "proteinContent": f"{per_serving['protein']:.1f} g",
                "fatContent": f"{per_serving['fat']:.1f} g",
                "carbohydrateContent": f"{per_serving['carbs']:.1f} g",
            }
        if rating_count:
            data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": rating_avg,
                "ratingCount": rating_count,
                "bestRating": 5,
                "worstRating": 1,
            }
        return data

    # ---------- komentarze i oceny czytelników ----------
    VOTER_COOKIE = "voter_id"
    VOTER_COOKIE_MAX_AGE = 2 * 365 * 24 * 3600
    # Formularz wysłany szybciej niż w tyle sekund od wyświetlenia strony to niemal na pewno bot.
    COMMENT_MIN_SECONDS = 3
    COMMENT_THANKS = "Dziękujemy! Komentarz pojawi się po zatwierdzeniu przez moderatora."

    def _hmac_hex(value: str) -> str:
        """HMAC-SHA256 z SECRET_KEY - pozwala porównywać identyfikatory bez przechowywania ich wprost."""
        return hmac.new(app.config["SECRET_KEY"].encode(), value.encode(), hashlib.sha256).hexdigest()

    def _voter_hash_from_cookie():
        token = request.cookies.get(VOTER_COOKIE, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token):
            return None
        return _hmac_hex("voter:" + token)

    def _rating_stats(recipe_ids):
        """Zwraca {recipe_id: (średnia, liczba ocen)} jednym zapytaniem."""
        if not recipe_ids:
            return {}
        rows = (
            db.session.query(RecipeRating.recipe_id, func.avg(RecipeRating.score), func.count(RecipeRating.id))
            .filter(RecipeRating.recipe_id.in_(recipe_ids))
            .group_by(RecipeRating.recipe_id)
            .all()
        )
        return {rid: (round(float(avg), 1), cnt) for rid, avg, cnt in rows}

    def _published_comments(target_filter):
        return (
            Comment.query.filter(target_filter, Comment.status == "published")
            .order_by(Comment.created_at.asc())
            .all()
        )

    def _sign_form_ts(ts: int) -> str:
        """Znacznik czasu wyświetlenia formularza + podpis HMAC ("1730000000.ab12...").
        Podpis sprawia, że bot nie może po prostu wysłać starej/wymyślonej wartości,
        żeby ominąć pułapkę czasową - musi najpierw pobrać stronę i odczekać."""
        return f"{ts}.{_hmac_hex(f'comment-form-ts:{ts}')}"

    def _form_ts_elapsed(value: str):
        """Sekundy od wyświetlenia formularza albo None, gdy znacznik jest brakujący/podrobiony."""
        ts, _, signature = (value or "").partition(".")
        expected = _hmac_hex(f"comment-form-ts:{ts}")
        # Porównanie na bajtach: compare_digest na str rzuca wyjątkiem dla znaków spoza ASCII.
        if not ts.isascii() or not ts.isdigit() or not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        return time.time() - int(ts)

    def _comment_form_context():
        return {
            "comment_form_ts": _sign_form_ts(int(time.time())),
            "comment_name_max": COMMENT_NAME_MAX,
            "comment_content_max": COMMENT_CONTENT_MAX,
        }

    def _handle_comment_post(target_kwargs, redirect_url):
        """Wspólna obsługa formularza komentarza pod przepisem i wpisem na blogu."""
        redirect_url += "#komentarze"
        # Pułapka na boty: pole niewidoczne dla ludzi oraz zbyt szybkie wysłanie formularza.
        # Botowi udajemy sukces, żeby nie wiedział, że został odrzucony.
        elapsed = _form_ts_elapsed(request.form.get("form_ts", ""))
        if request.form.get("website") or elapsed is None or elapsed < COMMENT_MIN_SECONDS:
            flash(COMMENT_THANKS, "success")
            return redirect(redirect_url)

        name = " ".join(request.form.get("author_name", "").split())
        content = request.form.get("content", "").strip()
        if not name or not content:
            flash("Podaj podpis i treść komentarza.", "error")
            return redirect(redirect_url)
        if len(name) > COMMENT_NAME_MAX or len(content) > COMMENT_CONTENT_MAX:
            flash(
                f"Komentarz jest za długi (podpis do {COMMENT_NAME_MAX}, treść do {COMMENT_CONTENT_MAX} znaków).",
                "error",
            )
            return redirect(redirect_url)

        db.session.add(
            Comment(
                author_name=name,
                content=content,
                status="pending",
                voter_hash=_hmac_hex("ip:" + (get_remote_address() or "")),
                **target_kwargs,
            )
        )
        db.session.commit()
        flash(COMMENT_THANKS, "success")
        return redirect(redirect_url)

    @app.route("/przepis/<slug>/komentarz", methods=["POST"])
    @limiter.limit(lambda: app.config["COMMENT_RATE_LIMIT"])
    def recipe_comment(slug):
        recipe = Recipe.query.filter_by(slug=slug, status="published").first_or_404()
        return _handle_comment_post({"recipe_id": recipe.id}, url_for("recipe_detail", slug=slug))

    @app.route("/przepis/<slug>/ocena", methods=["POST"])
    @limiter.limit(lambda: app.config["RATING_RATE_LIMIT"])
    def recipe_rate(slug):
        recipe = Recipe.query.filter_by(slug=slug, status="published").first_or_404()
        redirect_url = url_for("recipe_detail", slug=slug) + "#ocena"
        try:
            score = int(request.form.get("score", ""))
        except ValueError:
            score = 0
        if not 1 <= score <= 5:
            flash("Wybierz ocenę od 1 do 5 gwiazdek.", "error")
            return redirect(redirect_url)

        token = request.cookies.get(VOTER_COOKIE, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token):
            token = secrets.token_urlsafe(24)
        voter_hash = _hmac_hex("voter:" + token)

        rating = RecipeRating.query.filter_by(recipe_id=recipe.id, voter_hash=voter_hash).first()
        if rating:
            rating.score = score
            flash("Zmieniono Twoją ocenę przepisu.", "success")
        else:
            db.session.add(RecipeRating(recipe_id=recipe.id, score=score, voter_hash=voter_hash))
            flash("Dziękujemy za ocenę!", "success")
        db.session.commit()

        response = redirect(redirect_url)
        response.set_cookie(
            VOTER_COOKIE,
            token,
            max_age=VOTER_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=app.config.get("SESSION_COOKIE_SECURE", False),
        )
        return response

    # ---------- PWA: manifest, service worker, strona offline ----------
    @app.route("/manifest.webmanifest")
    def web_manifest():
        manifest = {
            "name": "Szczypta Smaku - przepisy i blog kulinarny",
            "short_name": "Szczypta Smaku",
            "description": "Przepisy kulinarne z listą zakupów, minutnikami i dostępem offline.",
            "lang": "pl",
            "start_url": "/?source=pwa",
            "scope": "/",
            "display": "standalone",
            "background_color": "#f8f1e8",
            "theme_color": "#a3461f",
            "icons": [
                {"src": url_for("static", filename="icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": url_for("static", filename="icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
                {
                    "src": url_for("static", filename="icons/maskable-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
            "shortcuts": [
                {"name": "Lista zakupów", "url": url_for("shopping_list")},
                {"name": "Ulubione", "url": url_for("favorites")},
            ],
        }
        response = app.response_class(json.dumps(manifest, ensure_ascii=False), mimetype="application/manifest+json")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @app.route("/sw.js")
    def service_worker():
        # Service worker musi być serwowany z katalogu głównego, żeby obejmował całą witrynę.
        response = send_file(os.path.join(app.static_folder, "js", "sw.js"), mimetype="text/javascript")
        # Przeglądarka ma zawsze sprawdzać nową wersję (aktualizacje aplikacji).
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/offline")
    def offline_page():
        return render_template("offline.html")

    @app.route("/polityka-prywatnosci")
    def privacy_policy():
        return render_template(
            "privacy.html",
            controller=app.config.get("PRIVACY_CONTROLLER", ""),
            contact_email=app.config.get("PRIVACY_CONTACT_EMAIL", ""),
        )

    # ---------- SEO: mapa witryny dla wyszukiwarek ----------
    @app.route("/sitemap.xml")
    def sitemap_xml():
        from xml.sax.saxutils import escape

        def entry(loc, lastmod=None):
            parts = [f"<loc>{escape(loc)}</loc>"]
            if lastmod:
                parts.append(f"<lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>")
            return "<url>" + "".join(parts) + "</url>"

        urls = [
            entry(url_for("index", _external=True)),
            entry(url_for("blog_index", _external=True)),
            entry(url_for("privacy_policy", _external=True)),
        ]
        for slug, updated in (
            db.session.query(Recipe.slug, Recipe.updated_at)
            .filter(Recipe.status == "published")
            .order_by(Recipe.id)
        ):
            urls.append(entry(url_for("recipe_detail", slug=slug, _external=True), updated))
        for slug, updated in (
            db.session.query(BlogPost.slug, BlogPost.updated_at)
            .filter(BlogPost.status == "published")
            .order_by(BlogPost.id)
        ):
            urls.append(entry(url_for("blog_detail", slug=slug, _external=True), updated))

        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls)
            + "\n</urlset>\n"
        )
        response = app.response_class(xml, mimetype="application/xml")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    @app.route("/robots.txt")
    def robots_txt():
        # Panele, logowanie i strony z danymi tylko z localStorage nie mają czego szukać w wynikach.
        disallowed = [
            "/admin",
            "/redakcja",
            "/login",
            "/logout",
            "/konto",
            "/api/",
            "/healthz",
            "/offline",
            "/lista-zakupow",
            "/ulubione",
        ]
        lines = ["User-agent: *", *(f"Disallow: {path}" for path in disallowed), ""]
        lines.append(f"Sitemap: {url_for('sitemap_xml', _external=True)}")
        response = app.response_class("\n".join(lines) + "\n", mimetype="text/plain")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    # ---------- lista zakupów i ulubione (dane w localStorage przeglądarki) ----------
    @app.route("/lista-zakupow")
    def shopping_list():
        return render_template("shopping_list.html")

    @app.route("/ulubione")
    def favorites():
        return render_template("favorites.html")

    @app.route("/api/przepisy")
    def api_recipes_by_slug():
        """Dane kart przepisów dla strony ulubionych: ?slugi=a,b,c (tylko opublikowane, max 100)."""
        slugs = [s.strip() for s in request.args.get("slugi", "").split(",") if s.strip()][:100]
        if not slugs:
            return jsonify(recipes=[])
        recipes = Recipe.query.filter(Recipe.slug.in_(slugs), Recipe.status == "published").all()
        stats = _rating_stats([r.id for r in recipes])
        return jsonify(
            recipes=[
                {
                    "slug": r.slug,
                    "title": r.title,
                    "description": r.description or "",
                    "url": url_for("recipe_detail", slug=r.slug),
                    "image_url": r.image_url or "",
                    "prep_time": r.prep_time_display,
                    "rating": stats.get(r.id, (None, 0))[0],
                }
                for r in recipes
            ]
        )

    # ---------- logowanie ----------
    def _post_login_redirect_endpoint():
        return "admin_dashboard" if current_user.is_admin else "redaktor_dashboard"

    # Jeden komunikat dla WSZYSTKICH niepowodzeń (zły login, złe hasło, konto zablokowane) -
    # nie ujawniamy atakującemu, które konta istnieją.
    LOGIN_FAILED_MESSAGE = (
        "Nieprawidłowa nazwa użytkownika lub hasło. "
        "Po wielu nieudanych próbach konto zostaje tymczasowo zablokowane."
    )

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit(app.config["LOGIN_RATE_LIMIT"], methods=["POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for(_post_login_redirect_endpoint()))

        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()

            if user is None:
                # Wykonujemy tak samo kosztowne sprawdzenie hasła (atrapa), żeby czas odpowiedzi
                # nie zdradzał, że takie konto nie istnieje.
                check_password_hash(_DUMMY_PASSWORD_HASH, password)
                app.logger.warning("Nieudane logowanie (nieznany login=%r, ip=%s)", username[:80], request.remote_addr)
            elif user.is_locked():
                # Zablokowane konto: nawet poprawne hasło nie działa (i nie zdradzamy tego w komunikacie).
                check_password_hash(_DUMMY_PASSWORD_HASH, password)
                app.logger.warning("Próba logowania na zablokowane konto %r (ip=%s)", user.username, request.remote_addr)
            elif user.check_password(password):
                user.register_successful_login()
                db.session.commit()
                login_user(user)
                app.logger.info("Zalogowano %r (rola=%s, ip=%s)", user.username, user.role, request.remote_addr)
                flash("Zalogowano pomyślnie.", "success")
                next_page = request.args.get("next")
                if is_safe_redirect_target(next_page):
                    return redirect(next_page)
                return redirect(url_for(_post_login_redirect_endpoint()))
            else:
                user.register_failed_login(
                    max_attempts=app.config["LOGIN_MAX_ATTEMPTS"],
                    lockout_minutes=app.config["LOGIN_LOCKOUT_MINUTES"],
                )
                db.session.commit()
                if user.is_locked():
                    app.logger.warning(
                        "Konto %r zablokowane na %s min po zbyt wielu nieudanych próbach (ip=%s)",
                        user.username, app.config["LOGIN_LOCKOUT_MINUTES"], request.remote_addr,
                    )
                else:
                    app.logger.warning("Nieudane logowanie na konto %r (ip=%s)", user.username, request.remote_addr)

            flash(LOGIN_FAILED_MESSAGE, "error")

        return render_template("login.html")

    @app.errorhandler(429)
    def rate_limit_exceeded(_e):
        return (
            render_template(
                "errors.html",
                code=429,
                message="Zbyt wiele prób logowania w krótkim czasie. Spróbuj ponownie za chwilę.",
            ),
            429,
        )

    @app.errorhandler(413)
    def file_too_large(_e):
        max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return (
            render_template(
                "errors.html",
                code=413,
                message=f"Przesłany plik jest za duży (limit: {max_mb} MB).",
            ),
            413,
        )

    @app.errorhandler(SecurityError)
    def untrusted_host(_e):
        # Nagłówek Host spoza TRUSTED_HOSTS. Bez szablonu: base.html buduje adresy bezwzględne
        # (og:image), a do tego potrzebna jest zaufana domena - render zakończyłby się błędem 500.
        return app.response_class("Nieprawidłowy nagłówek Host.", status=400, mimetype="text/plain")

    @app.errorhandler(400)
    def bad_request(_e):
        return render_template("errors.html", code=400, message="Nieprawidłowe żądanie."), 400

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return (
            render_template(
                "errors.html",
                code=400,
                message="Formularz wygasł lub jest nieprawidłowy. Odśwież stronę i spróbuj ponownie.",
            ),
            400,
        )

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return render_template("errors.html", code=405, message="Ta metoda nie jest dozwolona."), 405

    @app.errorhandler(500)
    def internal_error(_e):
        db.session.rollback()
        # Szczegóły błędu trafiają do logów serwera, użytkownik dostaje ogólny komunikat.
        return render_template("errors.html", code=500, message="Wystąpił błąd serwera. Spróbuj ponownie później."), 500

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        # POST + token CSRF: obca strona nie może wylogować użytkownika zwykłym linkiem/obrazkiem.
        app.logger.info("Wylogowano %r", current_user.username)
        # Wylogowanie kończy sesje na WSZYSTKICH urządzeniach - także skopiowane/wykradzione
        # ciasteczko przestaje działać.
        current_user.rotate_session_token()
        db.session.commit()
        logout_user()
        flash("Wylogowano.", "success")
        return redirect(url_for("index"))

    # ---------- zmiana własnego hasła (dostępna dla każdego zalogowanego) ----------
    @app.route("/konto/haslo", methods=["GET", "POST"])
    @login_required
    def change_own_password():
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            new_password_confirm = request.form.get("new_password_confirm", "")

            if not current_user.check_password(current_password):
                flash("Obecne hasło jest nieprawidłowe.", "error")
            elif new_password != new_password_confirm:
                flash("Nowe hasło i jego powtórzenie nie są takie same.", "error")
            elif new_password == current_password:
                flash("Nowe hasło musi różnić się od obecnego.", "error")
            else:
                password_error = validate_new_password(new_password, app.config["MIN_PASSWORD_LENGTH"])
                if password_error:
                    flash(password_error, "error")
                else:
                    user = current_user._get_current_object()
                    user.set_password(new_password)  # zmienia też znacznik sesji
                    db.session.commit()
                    # Inne urządzenia zostają wylogowane; bieżącą sesję odnawiamy nowym znacznikiem.
                    login_user(user)
                    app.logger.info("Użytkownik %r zmienił własne hasło", user.username)
                    flash("Hasło zostało zmienione. Pozostałe urządzenia zostały wylogowane.", "success")
                    return redirect(url_for(_post_login_redirect_endpoint()))

        return render_template(
            "account/change_password.html", min_password_length=app.config["MIN_PASSWORD_LENGTH"]
        )

    @app.route("/healthz")
    def healthz():
        """Sprawdzenie żywotności dla load balancera / Dockera. Nie ujawnia szczegółów."""
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - celowo łapiemy wszystko, zwracamy 503
            app.logger.exception("healthz: baza danych niedostępna")
            return jsonify(status="error"), 503
        return jsonify(status="ok")

    # ---------- panel administratora (CRUD) ----------
    @app.route("/admin")
    @login_required
    @admin_required
    def admin_dashboard():
        recipes = Recipe.query.order_by(Recipe.created_at.desc()).all()
        status_priority = {"pending": 0, "rejected": 1, "published": 2}
        recipes.sort(key=lambda r: status_priority.get(r.status, 3))
        pending_count = sum(1 for r in recipes if r.status == "pending")
        blog_pending_count = BlogPost.query.filter_by(status="pending").count()
        comments_pending_count = Comment.query.filter_by(status="pending").count()
        return render_template(
            "admin/dashboard.html",
            recipes=recipes,
            pending_count=pending_count,
            blog_pending_count=blog_pending_count,
            comments_pending_count=comments_pending_count,
        )

    @app.route("/admin/przepis/nowy", methods=["GET", "POST"])
    @login_required
    @admin_required
    def recipe_create():
        if request.method == "POST" and _recipe_numbers_ok():
            recipe = Recipe(author_id=current_user.id)
            recipe.publish()
            db.session.add(recipe)
            _save_recipe_form(recipe)
            db.session.commit()
            flash("Przepis został dodany.", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template(
            "admin/recipe_form.html",
            recipe=None,
            units=INGREDIENT_UNITS,
            pan_shapes=PAN_SHAPES,
            all_tags=Tag.query.order_by(Tag.name).all(),
            difficulties=DIFFICULTIES,
            form_action=url_for("recipe_create"),
            cancel_url=url_for("admin_dashboard"),
            editor_mode=False,
        )

    @app.route("/admin/przepis/<int:recipe_id>/edytuj", methods=["GET", "POST"])
    @login_required
    @admin_required
    def recipe_edit(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        if request.method == "POST" and _recipe_numbers_ok():
            _save_recipe_form(recipe)
            # Admin zapisujący formularz automatycznie zatwierdza przepis (jeśli czekał w kolejce).
            _approve_changes(recipe)
            db.session.commit()
            flash("Przepis został zaktualizowany i opublikowany.", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template(
            "admin/recipe_form.html",
            recipe=recipe,
            units=INGREDIENT_UNITS,
            pan_shapes=PAN_SHAPES,
            all_tags=Tag.query.order_by(Tag.name).all(),
            difficulties=DIFFICULTIES,
            form_action=url_for("recipe_edit", recipe_id=recipe.id),
            cancel_url=url_for("admin_dashboard"),
            editor_mode=False,
        )

    @app.route("/admin/przepis/<int:recipe_id>/usun", methods=["POST"])
    @login_required
    @admin_required
    def recipe_delete(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        _queue_image_cleanup(image_names_in(recipe.image_url, recipe.previous_image_url))
        db.session.delete(recipe)
        db.session.commit()
        flash("Przepis został usunięty.", "success")
        return redirect(url_for("admin_dashboard"))

    # ---------- kolejka redakcyjna: zatwierdzanie / odrzucanie ----------
    @app.route("/admin/kolejka")
    @login_required
    @admin_required
    def review_queue():
        pending = Recipe.query.filter_by(status="pending").order_by(Recipe.created_at.asc()).all()
        rejected = Recipe.query.filter_by(status="rejected").order_by(Recipe.created_at.desc()).all()
        return render_template("admin/queue.html", pending=pending, rejected=rejected)

    @app.route("/admin/przepis/<int:recipe_id>/zatwierdz", methods=["POST"])
    @login_required
    @admin_required
    def recipe_approve(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        _approve_changes(recipe)
        db.session.commit()
        flash(f"Przepis „{recipe.title}” został opublikowany.", "success")
        return redirect(url_for("review_queue"))

    @app.route("/admin/przepis/<int:recipe_id>/odrzuc", methods=["POST"])
    @login_required
    @admin_required
    def recipe_reject(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        recipe.status = "rejected"
        recipe.rejection_reason = request.form.get("reason", "").strip() or None
        restored = _restore_approved_image(recipe)
        db.session.commit()
        flash(f"Przepis „{recipe.title}” został odrzucony.{restored}", "success")
        return redirect(url_for("review_queue"))

    # ---------- zarządzanie kontami redaktorów ----------
    @app.route("/admin/redaktorzy")
    @login_required
    @admin_required
    def editors_page():
        editors = User.query.filter_by(role="redaktor").order_by(User.username).all()
        return render_template(
            "admin/editors.html", editors=editors, min_password_length=app.config["MIN_PASSWORD_LENGTH"]
        )

    @app.route("/admin/redaktorzy/nowy", methods=["POST"])
    @login_required
    @admin_required
    def editor_create():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        password_error = validate_new_password(password, app.config["MIN_PASSWORD_LENGTH"])
        if not username or not password:
            flash("Podaj nazwę użytkownika i hasło.", "error")
        elif len(username) > 80:
            flash("Nazwa użytkownika może mieć maksymalnie 80 znaków.", "error")
        elif password_error:
            flash(password_error, "error")
        elif User.query.filter_by(username=username).first():
            flash("Taka nazwa użytkownika jest już zajęta.", "error")
        else:
            user = User(username=username, role="redaktor")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            app.logger.info("Admin %r utworzył konto redaktora %r", current_user.username, username)
            flash(f"Utworzono konto redaktora: {username}.", "success")
        return redirect(url_for("editors_page"))

    @app.route("/admin/redaktorzy/<int:user_id>/reset-haslo", methods=["POST"])
    @login_required
    @admin_required
    def editor_reset_password(user_id):
        user = db.session.get(User, user_id) or abort(404)
        if user.role != "redaktor":
            abort(403)

        password = request.form.get("password", "")
        password_error = validate_new_password(password, app.config["MIN_PASSWORD_LENGTH"])
        if password_error:
            flash(password_error, "error")
        else:
            user.set_password(password)
            # Reset hasła odblokowuje też konto - redaktor mógł je stracić przez
            # zapomniane stare hasło i serię nieudanych prób logowania.
            user.register_successful_login()
            db.session.commit()
            app.logger.info(
                "Admin %r zresetował hasło redaktora %r", current_user.username, user.username
            )
            flash(f"Hasło redaktora {user.username} zostało zresetowane.", "success")
        return redirect(url_for("editors_page"))

    @app.route("/admin/redaktorzy/<int:user_id>/usun", methods=["POST"])
    @login_required
    @admin_required
    def editor_delete(user_id):
        user = db.session.get(User, user_id) or abort(404)
        if user.role != "redaktor":
            abort(403)
        # Przepisy usuwanego redaktora zostają, ale tracą powiązanie z autorem.
        Recipe.query.filter_by(author_id=user.id).update({"author_id": None})
        BlogPost.query.filter_by(author_id=user.id).update({"author_id": None})
        db.session.delete(user)
        db.session.commit()
        flash(f"Usunięto konto redaktora: {user.username}.", "success")
        return redirect(url_for("editors_page"))

    # ---------- panel redaktora (przepisy wymagają zatwierdzenia) ----------
    @app.route("/redakcja")
    @login_required
    @redaktor_or_admin_required
    def redaktor_dashboard():
        recipes = (
            Recipe.query.filter_by(author_id=current_user.id).order_by(Recipe.created_at.desc()).all()
        )
        posts = (
            BlogPost.query.filter_by(author_id=current_user.id).order_by(BlogPost.created_at.desc()).all()
        )
        return render_template("redaktor/dashboard.html", recipes=recipes, posts=posts)

    @app.route("/redakcja/przepis/nowy", methods=["GET", "POST"])
    @login_required
    @redaktor_or_admin_required
    def redaktor_recipe_create():
        if request.method == "POST" and _recipe_numbers_ok():
            recipe = Recipe(author_id=current_user.id, status="pending")
            db.session.add(recipe)
            _save_recipe_form(recipe)
            db.session.commit()
            flash("Przepis został wysłany do zatwierdzenia przez administratora.", "success")
            return redirect(url_for("redaktor_dashboard"))
        return render_template(
            "admin/recipe_form.html",
            recipe=None,
            units=INGREDIENT_UNITS,
            pan_shapes=PAN_SHAPES,
            all_tags=Tag.query.order_by(Tag.name).all(),
            difficulties=DIFFICULTIES,
            form_action=url_for("redaktor_recipe_create"),
            cancel_url=url_for("redaktor_dashboard"),
            editor_mode=True,
        )

    @app.route("/redakcja/przepis/<int:recipe_id>/edytuj", methods=["GET", "POST"])
    @login_required
    @redaktor_or_admin_required
    def redaktor_recipe_edit(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        if recipe.author_id != current_user.id and not current_user.is_admin:
            abort(403)
        if request.method == "POST" and _recipe_numbers_ok():
            approved_image_url = recipe.image_url
            _save_recipe_form(recipe)
            _hold_approved_image(recipe, approved_image_url)
            # Każda zmiana redaktora (nawet w już opublikowanym przepisie) wraca do kolejki
            # zatwierdzania - administrator musi ponownie potwierdzić treść.
            recipe.status = "pending"
            recipe.rejection_reason = None
            db.session.commit()
            flash("Zmiany zostały wysłane do ponownego zatwierdzenia.", "success")
            return redirect(url_for("redaktor_dashboard"))
        return render_template(
            "admin/recipe_form.html",
            recipe=recipe,
            units=INGREDIENT_UNITS,
            pan_shapes=PAN_SHAPES,
            all_tags=Tag.query.order_by(Tag.name).all(),
            difficulties=DIFFICULTIES,
            form_action=url_for("redaktor_recipe_edit", recipe_id=recipe.id),
            cancel_url=url_for("redaktor_dashboard"),
            editor_mode=True,
        )

    @app.route("/redakcja/przepis/<int:recipe_id>/usun", methods=["POST"])
    @login_required
    @redaktor_or_admin_required
    def redaktor_recipe_delete(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        if recipe.author_id != current_user.id and not current_user.is_admin:
            abort(403)
        # Sprawdzamy historię, nie bieżący status: edycja redaktora cofa przepis do kolejki,
        # więc sam status "pending" nie oznacza, że przepis nigdy nie był publiczny.
        if recipe.was_published and not current_user.is_admin:
            flash("Przepis, który był już opublikowany, może usunąć tylko administrator.", "error")
            return redirect(url_for("redaktor_dashboard"))
        _queue_image_cleanup(image_names_in(recipe.image_url, recipe.previous_image_url))
        db.session.delete(recipe)
        db.session.commit()
        flash("Przepis został usunięty.", "success")
        return redirect(url_for("redaktor_dashboard"))

    # ---------- blog: widoki publiczne ----------
    @app.route("/blog")
    def blog_index():
        posts = (
            BlogPost.query.filter_by(status="published")
            .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
            .all()
        )
        return render_template("blog/index.html", posts=posts)

    @app.route("/blog/<slug>")
    def blog_detail(slug):
        post = BlogPost.query.filter_by(slug=slug).first_or_404()
        if post.status != "published":
            # Niezatwierdzony wpis widzi tylko jego autor albo administrator.
            is_owner = current_user.is_authenticated and post.author_id == current_user.id
            is_admin_viewer = current_user.is_authenticated and current_user.is_admin
            if not (is_owner or is_admin_viewer):
                abort(404)
        if post.is_published:
            _count_view("blog", post.id)
        return render_template(
            "blog/detail.html",
            post=post,
            comments=_published_comments(Comment.blog_post_id == post.id),
            **_comment_form_context(),
        )

    @app.route("/blog/<slug>/komentarz", methods=["POST"])
    @limiter.limit(lambda: app.config["COMMENT_RATE_LIMIT"])
    def blog_comment(slug):
        post = BlogPost.query.filter_by(slug=slug, status="published").first_or_404()
        return _handle_comment_post({"blog_post_id": post.id}, url_for("blog_detail", slug=slug))

    # ---------- statystyki (administrator) ----------
    STATS_PERIODS = {7: "7 dni", 30: "30 dni", 90: "90 dni"}

    @app.route("/admin/statystyki")
    @login_required
    @admin_required
    def admin_stats():
        days = request.args.get("dni", 30, type=int)
        if days not in STATS_PERIODS:
            days = 30
        today = date.today()
        since = today - timedelta(days=days - 1)

        # Wyświetlenia dzień po dniu (z zerami dla dni bez wizyt - inaczej wykres by „skakał").
        per_day = dict(
            db.session.query(DailyView.day, func.sum(DailyView.views))
            .filter(DailyView.day >= since)
            .group_by(DailyView.day)
            .all()
        )
        daily = []
        for offset in range(days):
            day = since + timedelta(days=offset)
            daily.append({"day": day, "views": int(per_day.get(day, 0) or 0)})
        total_views = sum(d["views"] for d in daily)
        max_views = max((d["views"] for d in daily), default=0)

        def top_viewed(kind, model, limit=10):
            rows = (
                db.session.query(DailyView.object_id, func.sum(DailyView.views).label("views"))
                .filter(DailyView.kind == kind, DailyView.day >= since)
                .group_by(DailyView.object_id)
                .order_by(func.sum(DailyView.views).desc())
                .limit(limit)
                .all()
            )
            objects = {o.id: o for o in model.query.filter(model.id.in_([r[0] for r in rows])).all()}
            return [(objects[oid], int(v)) for oid, v in rows if oid in objects]

        top_recipes = top_viewed("recipe", Recipe)
        top_posts = top_viewed("blog", BlogPost)

        # Najlepiej oceniane (min. 1 głos) i aktywność czytelników w wybranym okresie.
        rating_rows = (
            db.session.query(
                RecipeRating.recipe_id, func.avg(RecipeRating.score), func.count(RecipeRating.id)
            )
            .group_by(RecipeRating.recipe_id)
            .order_by(func.avg(RecipeRating.score).desc(), func.count(RecipeRating.id).desc())
            .limit(10)
            .all()
        )
        rated = {r.id: r for r in Recipe.query.filter(Recipe.id.in_([r[0] for r in rating_rows])).all()}
        top_rated = [(rated[rid], round(float(avg), 1), cnt) for rid, avg, cnt in rating_rows if rid in rated]

        since_dt = datetime.combine(since, datetime.min.time())
        summary = {
            "views": total_views,
            "ratings": RecipeRating.query.filter(RecipeRating.updated_at >= since_dt).count(),
            "comments": Comment.query.filter(Comment.created_at >= since_dt).count(),
            "comments_pending": Comment.query.filter_by(status="pending").count(),
        }
        return render_template(
            "admin/stats.html",
            days=days,
            periods=STATS_PERIODS,
            daily=daily,
            max_views=max_views,
            summary=summary,
            top_recipes=top_recipes,
            top_posts=top_posts,
            top_rated=top_rated,
        )

    # ---------- moderacja komentarzy (administrator) ----------
    @app.route("/admin/komentarze")
    @login_required
    @admin_required
    def admin_comments():
        pending = Comment.query.filter_by(status="pending").order_by(Comment.created_at.asc()).all()
        recent = (
            Comment.query.filter_by(status="published").order_by(Comment.created_at.desc()).limit(50).all()
        )
        return render_template("admin/comments.html", pending=pending, recent=recent)

    @app.route("/admin/komentarz/<int:comment_id>/zatwierdz", methods=["POST"])
    @login_required
    @admin_required
    def comment_approve(comment_id):
        comment = db.session.get(Comment, comment_id) or abort(404)
        comment.status = "published"
        db.session.commit()
        flash("Komentarz został opublikowany.", "success")
        return redirect(url_for("admin_comments"))

    @app.route("/admin/komentarz/<int:comment_id>/usun", methods=["POST"])
    @login_required
    @admin_required
    def comment_delete(comment_id):
        comment = db.session.get(Comment, comment_id) or abort(404)
        db.session.delete(comment)
        db.session.commit()
        flash("Komentarz został usunięty.", "success")
        next_url = request.form.get("next")
        return redirect(next_url if is_safe_redirect_target(next_url) else url_for("admin_comments"))

    # ---------- blog: panel administratora ----------
    @app.route("/admin/blog")
    @login_required
    @admin_required
    def admin_blog():
        posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
        status_priority = {"pending": 0, "rejected": 1, "published": 2}
        posts.sort(key=lambda p: status_priority.get(p.status, 3))
        return render_template("admin/blog.html", posts=posts)

    @app.route("/admin/blog/nowy", methods=["GET", "POST"])
    @login_required
    @admin_required
    def blog_create():
        post = None
        if request.method == "POST":
            post = BlogPost(author_id=current_user.id)
            if _save_blog_form(post):
                post.publish()
                db.session.add(post)
                db.session.commit()
                flash("Wpis został opublikowany.", "success")
                return redirect(url_for("admin_blog"))
        return _render_blog_form(post, "blog_create", "admin_blog", editor_mode=False, is_new=True)

    @app.route("/admin/blog/<int:post_id>/edytuj", methods=["GET", "POST"])
    @login_required
    @admin_required
    def blog_edit(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        if request.method == "POST":
            if _save_blog_form(post):
                # Admin zapisujący formularz automatycznie zatwierdza wpis (jak przy przepisach).
                _approve_changes(post)
                db.session.commit()
                flash("Wpis został zaktualizowany i opublikowany.", "success")
                return redirect(url_for("admin_blog"))
            # Bez commita: niezapisane zmiany przepadną przy zamknięciu sesji, a formularz
            # pokaże wpisany przez autora tekst razem z komunikatem błędu.
        return _render_blog_form(post, "blog_edit", "admin_blog", editor_mode=False, is_new=False)

    @app.route("/admin/blog/<int:post_id>/usun", methods=["POST"])
    @login_required
    @admin_required
    def blog_delete(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        _queue_image_cleanup(image_names_in(post.image_url, post.previous_image_url, post.content))
        db.session.delete(post)
        db.session.commit()
        flash("Wpis został usunięty.", "success")
        return redirect(url_for("admin_blog"))

    @app.route("/admin/blog/<int:post_id>/zatwierdz", methods=["POST"])
    @login_required
    @admin_required
    def blog_approve(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        _approve_changes(post)
        db.session.commit()
        flash(f"Wpis „{post.title}” został opublikowany.", "success")
        return redirect(url_for("admin_blog"))

    @app.route("/admin/blog/<int:post_id>/odrzuc", methods=["POST"])
    @login_required
    @admin_required
    def blog_reject(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        post.status = "rejected"
        post.rejection_reason = request.form.get("reason", "").strip() or None
        restored = _restore_approved_image(post)
        db.session.commit()
        flash(f"Wpis „{post.title}” został odrzucony.{restored}", "success")
        return redirect(url_for("admin_blog"))

    # ---------- blog: panel redaktora (wpisy wymagają zatwierdzenia) ----------
    @app.route("/redakcja/blog/nowy", methods=["GET", "POST"])
    @login_required
    @redaktor_or_admin_required
    def redaktor_blog_create():
        post = None
        if request.method == "POST":
            post = BlogPost(author_id=current_user.id, status="pending")
            if _save_blog_form(post):
                db.session.add(post)
                db.session.commit()
                flash("Wpis został wysłany do zatwierdzenia przez administratora.", "success")
                return redirect(url_for("redaktor_dashboard"))
        return _render_blog_form(post, "redaktor_blog_create", "redaktor_dashboard", editor_mode=True, is_new=True)

    @app.route("/redakcja/blog/<int:post_id>/edytuj", methods=["GET", "POST"])
    @login_required
    @redaktor_or_admin_required
    def redaktor_blog_edit(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        if post.author_id != current_user.id and not current_user.is_admin:
            abort(403)
        if request.method == "POST":
            approved_image_url = post.image_url
            if _save_blog_form(post):
                _hold_approved_image(post, approved_image_url)
                # Każda zmiana redaktora wraca do kolejki zatwierdzania.
                post.status = "pending"
                post.rejection_reason = None
                db.session.commit()
                flash("Zmiany we wpisie zostały wysłane do ponownego zatwierdzenia.", "success")
                return redirect(url_for("redaktor_dashboard"))
        return _render_blog_form(post, "redaktor_blog_edit", "redaktor_dashboard", editor_mode=True, is_new=False)

    @app.route("/redakcja/blog/<int:post_id>/usun", methods=["POST"])
    @login_required
    @redaktor_or_admin_required
    def redaktor_blog_delete(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        if post.author_id != current_user.id and not current_user.is_admin:
            abort(403)
        # Jak przy przepisach: edycja cofa wpis do kolejki, więc liczy się historia publikacji.
        if post.was_published and not current_user.is_admin:
            flash("Wpis, który był już opublikowany, może usunąć tylko administrator.", "error")
            return redirect(url_for("redaktor_dashboard"))
        _queue_image_cleanup(image_names_in(post.image_url, post.previous_image_url, post.content))
        db.session.delete(post)
        db.session.commit()
        flash("Wpis został usunięty.", "success")
        return redirect(url_for("redaktor_dashboard"))

    # ---------- blog: zdjęcia w treści i podgląd (wywoływane przez edytor JS) ----------
    BLOG_MAX_IMAGES_PER_UPLOAD = 10

    @app.route("/redakcja/blog/zdjecia", methods=["POST"])
    @login_required
    @redaktor_or_admin_required
    def blog_upload_images():
        """Przyjmuje jedno lub kilka zdjęć naraz, zwraca ich adresy do wstawienia w treść.
        Token CSRF przychodzi w nagłówku X-CSRFToken (Flask-WTF sprawdza go automatycznie)."""
        files = [f for f in request.files.getlist("images") if f and f.filename]
        if not files:
            return jsonify(error="Nie wybrano żadnego zdjęcia."), 400
        if len(files) > BLOG_MAX_IMAGES_PER_UPLOAD:
            return jsonify(error=f"Naraz można wysłać najwyżej {BLOG_MAX_IMAGES_PER_UPLOAD} zdjęć."), 400

        images, errors = [], []
        for file in files:
            filename, error = _sanitize_and_save_image(file.read())
            if error:
                errors.append(f"{file.filename[:80]}: {error}")
                continue
            alt = os.path.splitext(file.filename)[0][:80]
            images.append({"url": url_for("static", filename=f"uploads/{filename}"), "alt": alt})
        app.logger.info("Użytkownik %r wgrał %s zdjęć do bloga", current_user.username, len(images))
        return jsonify(images=images, errors=errors), (200 if images else 400)

    @app.route("/redakcja/blog/podglad", methods=["POST"])
    @login_required
    @redaktor_or_admin_required
    def blog_preview():
        data = request.get_json(silent=True) or {}
        content = data.get("content")
        if not isinstance(content, str):
            return jsonify(error="Brak treści."), 400
        return jsonify(html=render_blog_markdown(content[:200_000]))

    def _render_blog_form(post, action_endpoint, cancel_endpoint, editor_mode, is_new):
        # Po nieudanej walidacji nowego wpisu `post` jest niezapisanym obiektem z danymi
        # z formularza - pokazujemy je ponownie, żeby autor nie stracił tekstu.
        form_action = (
            url_for(action_endpoint) if is_new else url_for(action_endpoint, post_id=post.id)
        )
        return render_template(
            "admin/blog_form.html",
            post=post,
            is_new=is_new,
            form_action=form_action,
            cancel_url=url_for(cancel_endpoint),
            editor_mode=editor_mode,
        )

    def _save_blog_form(post: BlogPost) -> bool:
        """Przepisuje dane z formularza do wpisu. Zwraca False (z komunikatem flash), gdy
        brakuje wymaganych pól - wtedy wywołujący nie zapisuje zmian."""
        _queue_image_cleanup(image_names_in(post.image_url, post.content))
        title = request.form.get("title", "").strip()[:150]
        content = request.form.get("content", "").strip()
        new_slug_needed = needs_new_slug(post, title)
        post.title = title
        post.excerpt = request.form.get("excerpt", "").strip()[:300] or None
        post.content = content
        if not title or not content:
            flash("Podaj tytuł i treść wpisu.", "error")
            return False

        with db.session.no_autoflush:
            base_slug = slugify(title) or "wpis"
            if new_slug_needed:
                candidate = base_slug
                counter = 2
                while BlogPost.query.filter(
                    BlogPost.slug == candidate, BlogPost.id != (post.id or -1)
                ).first():
                    candidate = f"{base_slug}-{counter}"
                    counter += 1
                post.slug = candidate

        new_image_url = _save_uploaded_image()
        if new_image_url:
            post.image_url = new_image_url
        elif request.form.get("remove_image") == "1":
            post.image_url = None
        return True

    # ---------- kopia zapasowa (eksport / import) ----------
    @app.route("/admin/kopia-zapasowa")
    @login_required
    @admin_required
    def backup_page():
        return render_template(
            "admin/backup.html",
            recipe_count=Recipe.query.count(),
            tag_count=Tag.query.count(),
            blog_post_count=BlogPost.query.count(),
            comment_count=Comment.query.count(),
            rating_count=RecipeRating.query.count(),
        )

    @app.route("/admin/kopia-zapasowa/eksport")
    @login_required
    @admin_required
    def backup_export():
        buffer = _build_backup_zip()
        filename = f"kopia-przepisow-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=filename,
        )

    @app.route("/admin/kopia-zapasowa/import", methods=["POST"])
    @login_required
    @admin_required
    def backup_import():
        file = request.files.get("backup_file")
        mode = request.form.get("mode", "merge")

        if not file or not file.filename:
            flash("Wybierz plik kopii zapasowej (.zip).", "error")
            return redirect(url_for("backup_page"))

        if not file.filename.lower().endswith(".zip"):
            flash("Plik musi być archiwum .zip wygenerowanym przez tę aplikację.", "error")
            return redirect(url_for("backup_page"))

        try:
            with zipfile.ZipFile(file.stream) as zf:
                # Ochrona przed „bombą ZIP": mały plik, który po rozpakowaniu zajmuje gigabajty.
                infos = zf.infolist()
                max_bytes = app.config["BACKUP_MAX_UNCOMPRESSED_MB"] * 1024 * 1024
                if len(infos) > app.config["BACKUP_MAX_ENTRIES"] or sum(i.file_size for i in infos) > max_bytes:
                    flash("Archiwum jest zbyt duże po rozpakowaniu - import odrzucony.", "error")
                    return redirect(url_for("backup_page"))

                with zf.open("recipes.json") as fh:
                    manifest = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                if not isinstance(manifest, dict) or not isinstance(manifest.get("recipes", []), list):
                    flash("Plik recipes.json ma nieprawidłową strukturę.", "error")
                    return redirect(url_for("backup_page"))

                # Import może zastąpić dowolne zdjęcie, a kopia może zawierać zdjęcia, których nic
                # nie użyje (np. w trybie "Dodaj tylko nowe") - sprawdzamy jedne i drugie po imporcie.
                _queue_image_cleanup(_referenced_image_names())

                if mode == "wipe":
                    # Czyścimy najpierw tabelę pośredniczącą (SQLAlchemy nie robi tego
                    # automatycznie przy masowym Query.delete()), potem przepisy i tagi.
                    db.session.execute(recipe_tags.delete())
                    Recipe.query.delete()
                    Tag.query.delete()
                    # Wpisy na blogu też są częścią kopii (od wersji 2 formatu). Komentarze do
                    # przepisów i wpisów usuwa baza (ON DELETE CASCADE).
                    if isinstance(manifest.get("blog_posts"), list):
                        BlogPost.query.delete()

                image_name_map = _extract_backup_images(zf)
                _queue_image_cleanup(image_name_map.values())

                created = updated = 0
                skipped = []
                for entry in manifest.get("recipes", []):
                    recipe, note = (
                        _restore_recipe_from_backup(entry, mode, image_name_map)
                        if isinstance(entry, dict) else (None, "nieprawidłowa pozycja")
                    )
                    if recipe is None:
                        skipped.append(note)
                    elif note.startswith("utworzono"):
                        created += 1
                    else:
                        updated += 1

                posts_created = posts_updated = posts_skipped = 0
                blog_posts = manifest.get("blog_posts")
                for entry in blog_posts if isinstance(blog_posts, list) else []:
                    post, action = (
                        _restore_blog_post_from_backup(entry, mode, image_name_map)
                        if isinstance(entry, dict) else (None, "nieprawidłowa pozycja")
                    )
                    if post is None:
                        posts_skipped += 1
                    elif action == "utworzono":
                        posts_created += 1
                    else:
                        posts_updated += 1

                reader_stats = _restore_reader_data(manifest, mode)
                db.session.commit()

            app.logger.info(
                "Admin %r zaimportował kopię zapasową (tryb=%s, utworzono=%s, zaktualizowano=%s)",
                current_user.username, mode, created, updated,
            )
            summary = f"Import zakończony: utworzono {created}, zaktualizowano {updated} przepisów."
            if skipped:
                summary += f" Pominięto {len(skipped)} pozycji."
            if isinstance(manifest.get("blog_posts"), list):
                summary += f" Wpisy na blogu: utworzono {posts_created}, zaktualizowano {posts_updated}."
                if posts_skipped:
                    summary += f" Pominięto {posts_skipped} wpisów."
            summary += (
                f" Komentarze: dodano {reader_stats['comments']}."
                f" Oceny: dodano {reader_stats['ratings_new']}, zmieniono {reader_stats['ratings_updated']}."
            )
            if reader_stats["skipped"]:
                summary += (
                    f" Pominięto {reader_stats['skipped']} komentarzy/ocen"
                    " (np. dotyczących wpisów na blogu, których nie ma w tej bazie)."
                )
            flash(summary, "success")
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            db.session.rollback()
            flash(f"Nie udało się odczytać kopii zapasowej - nieprawidłowy plik ({exc}).", "error")
        except (AttributeError, TypeError, ValueError, IntegrityError):
            # Poprawny JSON o złej zawartości, np. liczba zamiast listy kroków albo powtórzony tag.
            db.session.rollback()
            app.logger.exception("Import kopii zapasowej przerwany: nieprawidłowa zawartość")
            flash("Kopia zapasowa ma nieprawidłową zawartość - nic nie zostało zaimportowane.", "error")

        return redirect(url_for("backup_page"))

    def _sanitize_and_save_image(file_bytes: bytes):
        """
        Weryfikuje, że `file_bytes` to naprawdę obraz w dozwolonym formacie, dekoduje go
        i zapisuje na dysk jako świeżo zakodowany plik pod losową nazwą - zamiast ufać
        rozszerzeniu pliku albo deklarowanemu typowi MIME (oba może sfałszować atakujący).

        Dzięki pełnemu zdekodowaniu i ponownemu zapisaniu obrazu:
        - odrzucamy pliki, które nie są prawidłowymi obrazami (np. przemianowany
          skrypt, plik-polyglot łączący obraz z HTML/JS, uszkodzony plik),
        - usuwamy wszelkie metadane EXIF (mogą zawierać dane lokalizacji GPS,
          model urządzenia itp. - ryzyko prywatności autora zdjęcia), a wskazaną w nich
          orientację zdjęcia nanosimy najpierw na piksele,
        - usuwamy dowolne dane doklejone do pliku poza właściwą treścią obrazu,
        - chronimy przed „bombami dekompresji" (plik deklarujący miliardy pikseli) -
          Pillow domyślnie rzuca tu wyjątkiem; dodatkowo ograniczamy maksymalny
          zapisywany wymiar, żeby nie przechowywać nadmiernie dużych plików.

        Zwraca (nazwa_pliku, None) przy sukcesie albo (None, komunikat_błędu).
        """
        if not file_bytes:
            return None, "Przesłany plik jest pusty."

        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.load()  # wymusza pełne zdekodowanie pikseli (wyłapuje uszkodzone/spreparowane pliki)
        except Image.DecompressionBombError:
            return None, "Obraz jest zbyt duży (zbyt wiele pikseli) - odrzucono ze względów bezpieczeństwa."
        except (UnidentifiedImageError, OSError, ValueError):
            return None, "Plik nie jest prawidłowym obrazem (dozwolone: PNG, JPG, GIF, WEBP)."

        detected_format = (image.format or "").upper()
        if detected_format not in SAFE_IMAGE_FORMATS:
            return None, "Niedozwolony format obrazka. Dozwolone: PNG, JPG, GIF, WEBP."

        max_dim = app.config["MAX_IMAGE_DIMENSION"]
        fits_max_dim = image.width <= max_dim and image.height <= max_dim

        # Animacje zapisujemy z wszystkimi klatkami. Zbyt duże (limit pikseli liczony łącznie dla
        # klatek, jak ochrona przed bombami dekompresji) zostają nieruchomym obrazem z 1. klatki.
        frames = 1 if detected_format == "MPO" else getattr(image, "n_frames", 1)
        save_kwargs = {}
        if frames > 1 and fits_max_dim and image.width * image.height * frames <= Image.MAX_IMAGE_PIXELS:
            try:
                save_kwargs = animation_save_options(image)
            except (OSError, ValueError, EOFError):
                return None, "Plik nie jest prawidłowym obrazem (dozwolone: PNG, JPG, GIF, WEBP)."
        else:
            # Telefon zapisuje zdjęcie „na boku” z tagiem orientacji, a EXIF usuwamy.
            image = ImageOps.exif_transpose(image)
            # Ograniczamy maksymalny wymiar - zmniejszamy proporcjonalnie, jeśli trzeba.
            if not fits_max_dim:
                image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        save_format = "JPEG" if detected_format == "MPO" else detected_format
        if save_format == "JPEG":
            # JPEG nie obsługuje kanału alfa/palety - konwertujemy do RGB.
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            save_kwargs["quality"] = 88

        ext = SAFE_IMAGE_FORMATS[save_format]
        filename = f"{uuid.uuid4().hex}.{ext}"
        target_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        try:
            # Zapis BEZ przekazywania oryginalnych metadanych (brak exif=...) -
            # to jawnie usuwa EXIF i wszystko poza samą siatką pikseli obrazu.
            image.save(target_path, format=save_format, **save_kwargs)
        except (OSError, ValueError, EOFError) as exc:
            return None, f"Nie udało się zapisać obrazu: {exc}"

        return filename, None

    def _queue_image_cleanup(names):
        """Zgłasza pliki, które mogą przestać być używane po tym żądaniu."""
        g.image_cleanup = g.get("image_cleanup", set()) | set(names)

    def _hold_approved_image(item, old_image_url):
        """Zachowuje zatwierdzone zdjęcie, które redaktor właśnie zastąpił albo usunął.
        Zdjęcie przepisu niepublikowanego ani kolejna podmiana przed decyzją nie są
        zatwierdzone, więc takich plików nie przechowujemy."""
        if item.was_published and old_image_url and old_image_url != item.image_url and not item.previous_image_url:
            item.previous_image_url = old_image_url

    def _approve_changes(item):
        """Publikuje przepis lub wpis i pozwala usunąć zachowane poprzednie zdjęcie."""
        _queue_image_cleanup(image_names_in(item.previous_image_url))
        item.previous_image_url = None
        item.publish()

    def _restore_approved_image(item) -> str:
        """Po odrzuceniu zmian wraca zatwierdzone zdjęcie. Zwraca dopisek do komunikatu."""
        if not item.previous_image_url:
            return ""
        _queue_image_cleanup(image_names_in(item.image_url))
        item.image_url = item.previous_image_url
        item.previous_image_url = None
        return " Przywrócono poprzednie zdjęcie."

    def _referenced_image_names() -> set:
        """Wszystkie pliki z static/uploads, do których odsyła baza."""
        rows = db.session.query(Recipe.image_url, Recipe.previous_image_url).all() + db.session.query(
            BlogPost.image_url, BlogPost.previous_image_url, BlogPost.content
        ).all()
        return image_names_in(*(value for row in rows for value in row))

    def _remove_image_files(names):
        for name in names:
            try:
                os.remove(os.path.join(app.config["UPLOAD_FOLDER"], name))
            except FileNotFoundError:
                pass
            except OSError:
                app.logger.exception("Nie udało się usunąć zdjęcia %s", name)

    def _save_uploaded_image():
        """Sanityzuje i zapisuje przesłany/wklejony plik graficzny, zwraca jego publiczny URL."""
        file = request.files.get("image")
        if not file or not file.filename:
            return None

        filename, error = _sanitize_and_save_image(file.read())
        if error:
            flash(error, "error")
            return None
        return url_for("static", filename=f"uploads/{filename}")

    # ---------- kopia zapasowa: budowanie eksportu ----------
    def _build_backup_zip():
        """Tworzy w pamięci archiwum ZIP: recipes.json (dane) + images/ (zdjęcia)."""
        buffer = io.BytesIO()
        added_images = set()

        def add_image(filename):
            """Dołącza zdjęcie z katalogu uploadów do archiwum (raz). Zwraca nazwę albo None."""
            if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
                return None
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if not os.path.isfile(image_path):
                return None
            if filename not in added_images:
                zf.write(image_path, arcname=f"images/{filename}")
                added_images.add(filename)
            return filename

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            recipes_data = []
            for recipe in Recipe.query.order_by(Recipe.id).all():
                image_filename = None
                if recipe.image_url:
                    candidate = recipe.image_url.rsplit("/", 1)[-1]
                    image_path = os.path.join(app.config["UPLOAD_FOLDER"], candidate)
                    if os.path.isfile(image_path):
                        image_filename = candidate
                        if candidate not in added_images:
                            zf.write(image_path, arcname=f"images/{candidate}")
                            added_images.add(candidate)

                recipes_data.append(
                    {
                        "title": recipe.title,
                        "slug": recipe.slug,
                        "description": recipe.description,
                        # Płaska lista dla wstecznej kompatybilności z narzędziami czytającymi
                        # starszy format kopii zapasowej (bez podziału na sekcje).
                        "ingredients": recipe.ingredients_list,
                        # Pełna struktura z podziałem na sekcje (np. "Ciasto"/"Krem") - używana
                        # przy imporcie w tej i nowszych wersjach aplikacji.
                        "ingredients_sections": recipe.ingredients_sections,
                        "instructions": recipe.instructions_list,
                        "servings": recipe.servings,
                        "prep_time_min": recipe.prep_time_min,
                        "difficulty": recipe.difficulty,
                        "pan_shape": recipe.pan_shape,
                        "pan_size_cm": recipe.pan_size_cm,
                        "pan_width_cm": recipe.pan_width_cm,
                        "pan_length_cm": recipe.pan_length_cm,
                        "tags": [tag.name for tag in recipe.tags],
                        "image_filename": image_filename,
                        "previous_image_filename": add_image(recipe.previous_image_url.rsplit("/", 1)[-1])
                        if recipe.previous_image_url
                        else None,
                        "status": recipe.status,
                        "rejection_reason": recipe.rejection_reason,
                        "published_at": recipe.published_at.isoformat() if recipe.published_at else None,
                        "author_username": recipe.author.username if recipe.author else None,
                        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
                        "updated_at": recipe.updated_at.isoformat() if recipe.updated_at else None,
                    }
                )

            blog_posts_data = []
            for post in BlogPost.query.order_by(BlogPost.id).all():
                image_filename = add_image(post.image_url.rsplit("/", 1)[-1]) if post.image_url else None
                # Zdjęcia wstawione w treść wpisu (Markdown: ![opis](/static/uploads/plik.jpg)).
                content_images = [
                    name for name in dict.fromkeys(BLOG_UPLOAD_REF_RE.findall(post.content or "")) if add_image(name)
                ]
                blog_posts_data.append(
                    {
                        "title": post.title,
                        "slug": post.slug,
                        "excerpt": post.excerpt,
                        "content": post.content,
                        "image_filename": image_filename,
                        "content_images": content_images,
                        "previous_image_filename": add_image(post.previous_image_url.rsplit("/", 1)[-1])
                        if post.previous_image_url
                        else None,
                        "status": post.status,
                        "rejection_reason": post.rejection_reason,
                        "author_username": post.author.username if post.author else None,
                        "created_at": post.created_at.isoformat() if post.created_at else None,
                        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
                        "published_at": post.published_at.isoformat() if post.published_at else None,
                    }
                )

            comments_data, ratings_data = _export_reader_data()
            manifest = {
                "app": "wielka-ksiega-przepisow",
                # 2 = dodane wpisy na blogu, komentarze i oceny (import nadal przyjmuje wersję 1).
                "format_version": 2,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "recipe_count": len(recipes_data),
                "recipes": recipes_data,
                "blog_post_count": len(blog_posts_data),
                "blog_posts": blog_posts_data,
                "comment_count": len(comments_data),
                "comments": comments_data,
                "rating_count": len(ratings_data),
                "ratings": ratings_data,
            }
            zf.writestr("recipes.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        buffer.seek(0)
        return buffer

    def _restore_previous_image(item, data: dict, image_name_map: dict):
        """Odtwarza zachowane poprzednie zdjęcie. Starsze kopie nie mają tego pola."""
        original = data.get("previous_image_filename")
        name = image_name_map.get(original) if isinstance(original, str) else None
        item.previous_image_url = url_for("static", filename=f"uploads/{name}") if name else None

    # ---------- kopia zapasowa: wpisy na blogu ----------
    def _restore_blog_post_from_backup(data: dict, mode: str, image_name_map: dict):
        """Tworzy albo aktualizuje (po slugu) wpis na blogu z kopii. Zwraca (wpis_lub_None, akcja)."""
        title = str(data.get("title") or "").strip()[:150]
        slug = (str(data.get("slug") or "").strip() or slugify(title))[:180]
        content = str(data.get("content") or "")
        if not slug or not title or not content.strip():
            return None, "pominięto wpis bez tytułu lub treści"

        post = BlogPost.query.filter_by(slug=slug).first()
        if post is None:
            author = User.query.filter_by(username=str(data.get("author_username") or "")).first()
            post = BlogPost(slug=slug, author_id=author.id if author else current_user.id)
            post.created_at = _parse_backup_datetime(data.get("created_at")) or datetime.utcnow()
            db.session.add(post)
            action = "utworzono"
        elif mode == "skip_existing":
            return None, f"pominięto (już istnieje): „{title}”"
        else:
            action = "zaktualizowano"

        # Zdjęcia z archiwum dostały nowe nazwy - podmieniamy odwołania w treści.
        def remap(match):
            new_name = image_name_map.get(match.group(1))
            return f"{BLOG_IMAGE_PREFIX}{new_name}" if new_name else match.group(0)

        post.title = title
        post.content = BLOG_UPLOAD_REF_RE.sub(remap, content)
        post.excerpt = str(data.get("excerpt") or "").strip()[:300] or None

        original_image = data.get("image_filename")
        if original_image and original_image in image_name_map:
            post.image_url = url_for("static", filename=f"uploads/{image_name_map[original_image]}")
        _restore_previous_image(post, data, image_name_map)

        status = data.get("status")
        post.status = status if status in RECIPE_STATUSES else "pending"
        post.rejection_reason = str(data.get("rejection_reason") or "").strip() or None
        post.published_at = _parse_backup_datetime(data.get("published_at"))
        if post.status == "published" and post.published_at is None:
            post.published_at = datetime.utcnow()
        return post, action

    # ---------- kopia zapasowa: komentarze i oceny czytelników ----------
    def _export_reader_data():
        """Komentarze (pod przepisami i wpisami) oraz oceny - powiązane z treścią po slugu,
        bo identyfikatory w bazie docelowej mogą być inne."""
        comments = []
        for c in Comment.query.order_by(Comment.id).all():
            if c.recipe is not None:
                target_type, target_slug = "recipe", c.recipe.slug
            elif c.blog_post is not None:
                target_type, target_slug = "blog", c.blog_post.slug
            else:
                continue
            comments.append(
                {
                    "target_type": target_type,
                    "target_slug": target_slug,
                    "author_name": c.author_name,
                    "content": c.content,
                    "status": c.status,
                    "voter_hash": c.voter_hash,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
            )
        ratings = [
            {
                "recipe_slug": r.recipe.slug,
                "score": r.score,
                # HMAC z SECRET_KEY - nie da się z niego odczytać IP ani ciasteczka. Po imporcie
                # na serwer z innym SECRET_KEY czytelnik zagłosuje po prostu „od nowa".
                "voter_hash": r.voter_hash,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in RecipeRating.query.order_by(RecipeRating.id).all()
            if r.recipe is not None
        ]
        return comments, ratings

    def _parse_backup_datetime(value):
        try:
            return datetime.fromisoformat(str(value).rstrip("Z")) if value else None
        except ValueError:
            return None

    def _restore_reader_data(manifest: dict, mode: str):
        """Przywraca komentarze i oceny z kopii. Komentarze nigdy się nie dublują (ten sam
        cel + podpis + treść = ten sam komentarz). Oceny: jedna na (przepis, głosujący) -
        w trybie „Dodaj tylko nowe" istniejąca ocena zostaje, w pozostałych jest nadpisywana.
        Zwraca słownik z licznikami."""
        stats = {"comments": 0, "ratings_new": 0, "ratings_updated": 0, "skipped": 0}
        db.session.flush()  # przepisy utworzone w tym imporcie muszą mieć już id
        recipe_ids = dict(db.session.query(Recipe.slug, Recipe.id).all())
        post_ids = dict(db.session.query(BlogPost.slug, BlogPost.id).all())

        existing_comments = {
            (c.recipe_id, c.blog_post_id, c.author_name, c.content)
            for c in db.session.query(Comment.recipe_id, Comment.blog_post_id, Comment.author_name, Comment.content)
        }
        hash_re = re.compile(r"[0-9a-f]{64}")

        for item in manifest.get("comments") or []:
            if not isinstance(item, dict):
                stats["skipped"] += 1
                continue
            slug = str(item.get("target_slug") or "")
            recipe_id = recipe_ids.get(slug) if item.get("target_type") == "recipe" else None
            post_id = post_ids.get(slug) if item.get("target_type") == "blog" else None
            name = " ".join(str(item.get("author_name") or "").split())[:COMMENT_NAME_MAX]
            content = str(item.get("content") or "").strip()[:COMMENT_CONTENT_MAX]
            if not (recipe_id or post_id) or not name or not content:
                stats["skipped"] += 1  # np. komentarz do wpisu na blogu, którego nie ma w tej bazie
                continue
            key = (recipe_id, post_id, name, content)
            if key in existing_comments:
                continue
            voter_hash = str(item.get("voter_hash") or "")
            db.session.add(
                Comment(
                    recipe_id=recipe_id,
                    blog_post_id=post_id,
                    author_name=name,
                    content=content,
                    status=item.get("status") if item.get("status") in COMMENT_STATUSES else "pending",
                    voter_hash=voter_hash if hash_re.fullmatch(voter_hash) else None,
                    created_at=_parse_backup_datetime(item.get("created_at")) or datetime.utcnow(),
                )
            )
            existing_comments.add(key)
            stats["comments"] += 1

        existing_ratings = {(r.recipe_id, r.voter_hash): r for r in RecipeRating.query.all()}
        for item in manifest.get("ratings") or []:
            if not isinstance(item, dict):
                stats["skipped"] += 1
                continue
            recipe_id = recipe_ids.get(str(item.get("recipe_slug") or ""))
            score = item.get("score")
            if not recipe_id or not isinstance(score, int) or not 1 <= score <= 5:
                stats["skipped"] += 1
                continue
            voter_hash = str(item.get("voter_hash") or "")
            if not hash_re.fullmatch(voter_hash):
                voter_hash = secrets.token_hex(32)  # głos bez identyfikatora - zachowujemy jako osobny
            rating = existing_ratings.get((recipe_id, voter_hash))
            if rating is not None:
                if mode != "skip_existing" and rating.score != score:
                    rating.score = score
                    stats["ratings_updated"] += 1
                continue
            rating = RecipeRating(
                recipe_id=recipe_id,
                score=score,
                voter_hash=voter_hash,
                created_at=_parse_backup_datetime(item.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_backup_datetime(item.get("updated_at")) or datetime.utcnow(),
            )
            db.session.add(rating)
            existing_ratings[(recipe_id, voter_hash)] = rating
            stats["ratings_new"] += 1
        return stats

    # ---------- kopia zapasowa: rozpakowywanie zdjęć z importu ----------
    def _extract_backup_images(zf: zipfile.ZipFile) -> dict:
        """Sanityzuje i zapisuje na dysk zdjęcia z archiwum (pod nowymi, losowymi nazwami).
        Zawartość ZIP-a traktujemy jako dane niezaufane - każdy plik przechodzi przez
        tę samą walidację/ponowne zakodowanie przez Pillow co zdjęcia wgrywane ręcznie.
        Zwraca mapę: oryginalna nazwa pliku w archiwum -> nowa nazwa pliku na dysku."""
        name_map = {}
        for entry_name in zf.namelist():
            if not entry_name.startswith("images/") or entry_name.endswith("/"):
                continue
            original_name = entry_name.split("/", 1)[1]
            if not original_name:
                continue

            with zf.open(entry_name) as src:
                file_bytes = src.read()

            filename, error = _sanitize_and_save_image(file_bytes)
            if error:
                # Pomijamy pojedyncze uszkodzone/nieprawidłowe zdjęcie - nie przerywamy
                # całego importu z powodu jednego złego pliku w archiwum.
                continue
            name_map[original_name] = filename
        return name_map

    # ---------- kopia zapasowa: odtwarzanie pojedynczego przepisu ----------
    def _backup_count(value):
        """Nieujemna liczba całkowita z pliku kopii zapasowej albo None (json przepuszcza też NaN)."""
        if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= MAX_BACKUP_COUNT:
            return int(value)
        return None

    def _restore_recipe_from_backup(data: dict, mode: str, image_name_map: dict):
        """Tworzy nowy przepis albo aktualizuje istniejący (po slugu) na podstawie
        wpisu z pliku recipes.json. Zwraca (recipe_lub_None, opis_akcji)."""
        title = str(data.get("title") or "").strip()
        slug = str(data.get("slug") or "").strip() or slugify(title)
        if not slug:
            return None, "pominięto pozycję bez tytułu i sluga"

        with db.session.no_autoflush:
            recipe = Recipe.query.filter_by(slug=slug).first()

            if recipe is None:
                author = User.query.filter_by(username=str(data.get("author_username") or "")).first()
                recipe = Recipe(slug=slug, author_id=author.id if author else current_user.id)
                recipe.created_at = _parse_backup_datetime(data.get("created_at")) or datetime.utcnow()
                recipe.updated_at = _parse_backup_datetime(data.get("updated_at")) or recipe.created_at
                db.session.add(recipe)
                note_prefix = "utworzono"
            elif mode == "skip_existing":
                return None, f"pominięto (już istnieje): „{title or slug}”"
            else:
                note_prefix = "zaktualizowano"

            recipe.title = title or recipe.title or "Bez tytułu"
            recipe.description = str(data.get("description") or "").strip()

            entries = []
            sections_data = data.get("ingredients_sections")
            if isinstance(sections_data, list) and sections_data:
                for index, section in enumerate(sections_data):
                    if not isinstance(section, dict):
                        continue
                    section_name = section.get("name")
                    # Pierwsza, nienazwana sekcja nie potrzebuje nagłówka; kolejne nienazwane
                    # wracają do "listy bez sekcji" pustym nagłówkiem.
                    if section_name or entries:
                        entries.append({"type": "section", "name": section_name or ""})
                    for item in section.get("items") or []:
                        if isinstance(item, dict):
                            entries.append({**item, "type": "item"})
            else:
                # Starszy format kopii zapasowej: płaska lista składników bez sekcji.
                for item in data.get("ingredients") or []:
                    if isinstance(item, dict):
                        entries.append({**item, "type": "item"})
            recipe.ingredients = serialize_ingredient_entries(entries)

            steps = [str(s).strip() for s in (data.get("instructions") or []) if str(s).strip()]
            recipe.instructions = "\n".join(steps)

            recipe.servings = _backup_count(data.get("servings"))
            prep_time = data.get("prep_time_min")
            recipe.prep_time_min = (
                int(prep_time) if isinstance(prep_time, (int, float)) and 0 < prep_time <= 10080 else None
            )
            difficulty = data.get("difficulty")
            recipe.difficulty = difficulty if difficulty in DIFFICULTIES else None

            pan_shape = data.get("pan_shape")
            recipe.pan_shape = pan_shape if pan_shape in PAN_SHAPES else None
            recipe.pan_size_cm = _backup_count(data.get("pan_size_cm")) if recipe.pan_shape == "okragla" else None
            is_rectangular = recipe.pan_shape == "prostokatna"
            recipe.pan_width_cm = _backup_count(data.get("pan_width_cm")) if is_rectangular else None
            recipe.pan_length_cm = _backup_count(data.get("pan_length_cm")) if is_rectangular else None

            tags = []
            for name in data.get("tags") or []:
                name = str(name).strip()
                if not name:
                    continue
                tag_slug = slugify(name)
                if not tag_slug:
                    continue
                tag = Tag.query.filter_by(slug=tag_slug).first()
                if tag is None:
                    tag = Tag(name=name, slug=tag_slug)
                    db.session.add(tag)
                    # Flush natychmiast: przy imporcie wielu przepisów z tym samym NOWYM
                    # tagiem, no_autoflush uniemożliwiłby kolejnemu zapytaniu zobaczenie
                    # tego taga, co prowadziło do próby utworzenia go drugi raz (błąd
                    # unikalności slug). Jawny flush sprawia, że tag jest już widoczny
                    # dla zapytań w kolejnych iteracjach pętli po przepisach.
                    db.session.flush()
                if tag not in tags:
                    tags.append(tag)
            recipe.tags = tags

            status = data.get("status")
            recipe.status = status if status in RECIPE_STATUSES else "published"
            recipe.rejection_reason = str(data.get("rejection_reason") or "").strip() or None
            # Starsze kopie nie mają tego pola - wtedy zostaje dotychczasowa data.
            recipe.published_at = _parse_backup_datetime(data.get("published_at")) or recipe.published_at
            if recipe.status == "published" and recipe.published_at is None:
                recipe.published_at = datetime.utcnow()

            # Zdjęcie podmieniamy tylko, jeśli archiwum je zawierało; w przeciwnym razie
            # zostawiamy dotychczasowe (przy aktualizacji) albo brak zdjęcia (przy nowym).
            original_image_name = data.get("image_filename")
            if original_image_name and original_image_name in image_name_map:
                recipe.image_url = url_for(
                    "static", filename=f"uploads/{image_name_map[original_image_name]}"
                )
            _restore_previous_image(recipe, data, image_name_map)

        return recipe, f"{note_prefix}: „{recipe.title}”"

    def _ingredient_entries_from_form():
        """
        Zwraca wpisy składników z formularza. Preferuje ustrukturyzowane pole
        `ingredients_structured` (JSON zbudowany przez JS tuż przed wysłaniem formularza -
        pozwala przeplatać nagłówki sekcji ze zwykłymi składnikami w dowolnej kolejności).
        Jeśli go brak (np. JS wyłączony), spada do starych, płaskich pól name[]/amount[]/unit[]
        bez podziału na sekcje - formularz nadal da się wypełnić.
        """
        raw_structured = request.form.get("ingredients_structured", "").strip()
        entries = None
        if raw_structured:
            try:
                parsed = json.loads(raw_structured)
                if isinstance(parsed, list):
                    entries = parsed
            except (ValueError, TypeError):
                entries = None

        if entries is None:
            # Tryb awaryjny bez JS: płaskie pola, bez podziału na sekcje.
            amounts = request.form.getlist("ingredient_amount[]")
            units = request.form.getlist("ingredient_unit[]")
            names = request.form.getlist("ingredient_name[]")
            kcals = request.form.getlist("ingredient_kcal[]")
            proteins = request.form.getlist("ingredient_protein[]")
            fats = request.form.getlist("ingredient_fat[]")
            carbs_list = request.form.getlist("ingredient_carbs[]")
            entries = [
                {
                    "type": "item", "amount": a, "unit": u, "name": n,
                    "kcal": k, "protein": p, "fat": f, "carbs": c,
                }
                for a, u, n, k, p, f, c in zip(amounts, units, names, kcals, proteins, fats, carbs_list)
            ]

        return entries

    def _recipe_numbers_ok() -> bool:
        """False (z komunikatem flash), gdy formularz zawiera wartość ujemną - wtedy wywołujący
        nie zapisuje przepisu. Przeglądarka też to blokuje, ale żądanie można wysłać z pominięciem
        formularza. Sprawdzamy przed zmianą obiektu, więc odrzucenie niczego nie nadpisuje."""
        values = [
            request.form.get(field)
            for field in ("servings", "prep_time_min", "pan_size_cm", "pan_width_cm", "pan_length_cm")
        ]
        for entry in _ingredient_entries_from_form():
            if isinstance(entry, dict) and entry.get("type") == "item":
                values += [entry.get(key) for key in ("amount", "kcal", "protein", "fat", "carbs")]
        if any(is_negative_text(value) for value in values):
            flash("Wartości liczbowe w przepisie nie mogą być ujemne.", "error")
            return False
        return True

    def _build_instructions_text():
        steps = [s.strip() for s in request.form.getlist("step[]") if s.strip()]
        return "\n".join(steps)

    def _save_tags(recipe: Recipe):
        raw = request.form.get("tags", "")
        names = []
        seen = set()
        for part in raw.split(","):
            name = part.strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            names.append(name)

        tags = []
        for name in names:
            tag_slug = slugify(name) or None
            if not tag_slug:
                continue
            tag = Tag.query.filter_by(slug=tag_slug).first()
            if tag is None:
                tag = Tag(name=name, slug=tag_slug)
                db.session.add(tag)
                # Flush natychmiast, żeby dwie różne nazwy dające ten sam slug w jednym
                # zgłoszeniu (np. "Deser" i "deser!") nie próbowały utworzyć taga dwukrotnie.
                db.session.flush()
            if tag not in tags:
                tags.append(tag)
        recipe.tags = tags

    def _save_recipe_form(recipe: Recipe):
        _queue_image_cleanup(image_names_in(recipe.image_url))
        title = request.form.get("title", "").strip()
        new_slug_needed = needs_new_slug(recipe, title)
        recipe.title = title

        # Wszelkie zapytania do bazy w trakcie wypełniania formularza (sprawdzanie unikalności
        # sluga, wyszukiwanie/tworzenie tagów) mogłyby wywołać przedwczesny autoflush sesji,
        # zanim przepis ma komplet wymaganych pól - stąd blok no_autoflush.
        with db.session.no_autoflush:
            # Slug generujemy tylko jeśli tytuł się zmienił / to nowy przepis
            base_slug = slugify(title) or "przepis"
            if new_slug_needed:
                candidate = base_slug
                counter = 2
                while Recipe.query.filter(
                    Recipe.slug == candidate, Recipe.id != (recipe.id or -1)
                ).first():
                    candidate = f"{base_slug}-{counter}"
                    counter += 1
                recipe.slug = candidate

            recipe.description = request.form.get("description", "").strip()
            recipe.ingredients = serialize_ingredient_entries(_ingredient_entries_from_form())
            recipe.instructions = _build_instructions_text()
            _save_tags(recipe)

        # Zdjęcie: jeśli przesłano nowy plik, zastępuje poprzedni; w innym razie zostaje bez zmian
        new_image_url = _save_uploaded_image()
        if new_image_url:
            recipe.image_url = new_image_url
        elif request.form.get("remove_image") == "1":
            recipe.image_url = None

        # Forma do pieczenia: okrągła (średnica) albo prostokątna (dwa wymiary)
        pan_shape = request.form.get("pan_shape", "").strip()
        recipe.pan_shape = pan_shape if pan_shape in PAN_SHAPES else None

        if recipe.pan_shape == "okragla":
            pan_size = request.form.get("pan_size_cm", "").strip()
            recipe.pan_size_cm = form_count(pan_size)
            recipe.pan_width_cm = None
            recipe.pan_length_cm = None
        elif recipe.pan_shape == "prostokatna":
            pan_width = request.form.get("pan_width_cm", "").strip()
            pan_length = request.form.get("pan_length_cm", "").strip()
            recipe.pan_width_cm = form_count(pan_width)
            recipe.pan_length_cm = form_count(pan_length)
            recipe.pan_size_cm = None
        else:
            recipe.pan_size_cm = None
            recipe.pan_width_cm = None
            recipe.pan_length_cm = None

        servings = request.form.get("servings", "").strip()
        recipe.servings = form_count(servings)

        prep_time = request.form.get("prep_time_min", "").strip()
        prep_time = form_count(prep_time)
        recipe.prep_time_min = prep_time if prep_time and prep_time <= 10080 else None
        difficulty = request.form.get("difficulty", "").strip()
        recipe.difficulty = difficulty if difficulty in DIFFICULTIES else None

    # ---------- obsługa błędów ----------
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors.html", code=403, message="Brak dostępu."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors.html", code=404, message="Nie znaleziono strony."), 404

    # ---------- komendy CLI ----------
    def _read_password(password, env_name="ADMIN_PASSWORD"):
        """Hasło z opcji, potem ze zmiennej środowiskowej, na końcu interaktywnie (bez echa)."""
        password = password or os.environ.get(env_name)
        if not password:
            password = click.prompt("Hasło", hide_input=True, confirmation_prompt=True)
        error = validate_new_password(password, app.config["MIN_PASSWORD_LENGTH"])
        if error:
            raise click.ClickException(error)
        return password

    def _upsert_user(username, password, role):
        if not username or len(username) > 80:
            raise click.ClickException("Nazwa użytkownika musi mieć od 1 do 80 znaków.")
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, role=role)
            db.session.add(user)
            action = "Utworzono"
        else:
            action = "Zaktualizowano hasło dla"
        user.set_password(password)
        user.role = role
        user.register_successful_login()  # odblokowuje konto i zeruje licznik nieudanych prób
        db.session.commit()
        return action

    @app.cli.command("create-admin")
    @click.option("--username", default=None, help="Nazwa użytkownika (domyślnie: ADMIN_USERNAME lub 'admin').")
    @click.option("--password", default=None, help="Hasło (jeśli pominięte: ADMIN_PASSWORD albo pytanie interaktywne).")
    def create_admin(username, password):
        """Tworzy (lub aktualizuje hasło) konta administratora."""
        username = username or os.environ.get("ADMIN_USERNAME") or "admin"
        password = _read_password(password, "ADMIN_PASSWORD")
        click.echo(f"{_upsert_user(username, password, 'admin')} administratora: {username}")

    @app.cli.command("create-redaktor")
    @click.option("--username", required=True, help="Nazwa użytkownika redaktora.")
    @click.option("--password", default=None, help="Hasło (jeśli pominięte: pytanie interaktywne).")
    def create_redaktor(username, password):
        """Tworzy (lub aktualizuje hasło) konta redaktora."""
        password = _read_password(password, "REDAKTOR_PASSWORD")
        click.echo(f"{_upsert_user(username, password, 'redaktor')} redaktora: {username}")

    @app.cli.command("unlock-user")
    @click.option("--username", required=True, help="Konto do odblokowania.")
    def unlock_user(username):
        """Zdejmuje blokadę logowania z konta (np. gdy admin sam się zablokował)."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException(f"Nie ma użytkownika {username!r}.")
        user.register_successful_login()
        db.session.commit()
        click.echo(f"Odblokowano konto: {username}")

    @app.cli.command("cleanup-images")
    @click.option("--apply", is_flag=True, help="Naprawdę usuń pliki (bez tego tylko je wypisuje).")
    @click.option("--min-age-hours", default=24, show_default=True, type=click.IntRange(min=1),
                  help="Pomija nowsze pliki - zdjęcia wgrane do wpisu, który nie został jeszcze zapisany.")
    def cleanup_images(apply, min_age_hours):
        """Znajduje w static/uploads pliki, do których nic nie odsyła (np. zdjęcia z niezapisanych wpisów)."""
        used = _referenced_image_names()
        if not used:
            # Puste odwołania to najpewniej zła baza (DATABASE_URL), a nie brak zdjęć.
            raise click.ClickException("Baza nie odsyła do żadnego zdjęcia - przerywam, sprawdź DATABASE_URL.")
        folder = app.config["UPLOAD_FOLDER"]
        newest_allowed = time.time() - min_age_hours * 3600
        unused = [
            name for name in sorted(os.listdir(folder))
            if image_names_in(f"/static/uploads/{name}") == {name}
            and name not in used
            and os.path.getmtime(os.path.join(folder, name)) < newest_allowed
        ]
        for name in unused:
            click.echo(name)
        if apply:
            _remove_image_files(unused)
        click.echo(f"{'Usunięto' if apply else 'Do usunięcia (dodaj --apply)'}: {len(unused)}")

    @app.cli.command("export-backup")
    @click.option("--output", "-o", required=True, type=click.Path(dir_okay=False, writable=True),
                  help="Ścieżka pliku .zip do zapisania (dla cron: np. /backups/przepisy-$(date +%F).zip).")
    def export_backup(output):
        """Zapisuje kopię zapasową (przepisy + zdjęcia) bez logowania w przeglądarce - do zadań cron."""
        buffer = _build_backup_zip()
        with open(output, "wb") as fh:
            fh.write(buffer.getvalue())
        os.chmod(output, 0o600)  # kopia zawiera całą treść serwisu
        click.echo(f"Zapisano kopię zapasową: {output} ({os.path.getsize(output)} B)")

    return app


if __name__ == "__main__":
    # Wygodne uruchomienie lokalne: APP_ENV=development python app.py
    # Na produkcji NIE używaj tego - uruchamiaj gunicorna (patrz wsgi.py / DEPLOYMENT.md).
    _dev_app = create_app()
    if _dev_app.config["APP_ENV"] != "development":
        raise SystemExit("Serwer deweloperski działa tylko przy APP_ENV=development. Na produkcji użyj gunicorna.")
    _dev_app.run(debug=True)
