import io
import json
import logging
import os
import re
import secrets
import sqlite3
import unicodedata
import uuid
import zipfile
from datetime import datetime
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
from PIL import Image, UnidentifiedImageError
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from config import get_config, validate_production_config
from models import (
    INGREDIENT_UNITS,
    PAN_SHAPES,
    RECIPE_STATUSES,
    ROLES,
    BlogPost,
    Recipe,
    Tag,
    User,
    db,
    recipe_tags,
    render_blog_markdown,
)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Zaloguj się, aby uzyskać dostęp do tej strony."
login_manager.session_protection = "basic"
csrf = CSRFProtect()
migrate = Migrate()

# Fikcyjny hash używany, gdy podany login nie istnieje — dzięki temu czas odpowiedzi
# nie zdradza, czy konto istnieje (bez tego brak sprawdzania hasła byłby wyraźnie szybszy).
_DUMMY_PASSWORD_HASH = generate_password_hash("nieistniejace-konto-atrapa")

# Hasła, które odrzucamy niezależnie od długości.
WEAK_PASSWORDS = {"zmien-to-haslo", "password", "haslo12345", "1234567890", "qwertyuiop"}

# Formaty obrazów, które potrafimy bezpiecznie zdekodować i ponownie zapisać przez Pillow.
# Mapowanie: format wykryty przez Pillow -> rozszerzenie pliku zapisywanego na dysku.
SAFE_IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


def slugify(text: str) -> str:
    """Zamienia tytuł przepisu na URL-owy 'slug', np. 'Żurek Śląski' -> 'zurek-slaski'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)


def _clean_line_field(value) -> str:
    """Usuwa znaki, które zepsułyby zapis składników linia-po-linii ("|" i nowe linie)."""
    return re.sub(r"[|\r\n]+", " ", str(value if value is not None else "")).strip()


def serialize_ingredient_entries(entries) -> str:
    """
    Zamienia listę wpisów [{"type": "section", "name": ...}, {"type": "item", "amount": ...,
    "unit": ..., "name": ...}] na tekst zapisywany w Recipe.ingredients. Jedno miejsce dla
    formularza i importu kopii zapasowej — dzięki temu dane z obu źródeł są tak samo czyszczone.
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
            # amount jest pierwszym polem linii — nie może przypadkiem wyglądać jak nagłówek sekcji
            amount = _clean_line_field(entry.get("amount")).replace(Recipe.SECTION_MARKER, "")
            unit = _clean_line_field(entry.get("unit"))
            kcal = _clean_line_field(entry.get("kcal"))
            protein = _clean_line_field(entry.get("protein"))
            fat = _clean_line_field(entry.get("fat"))
            carbs = _clean_line_field(entry.get("carbs"))
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


def validate_new_password(password: str, min_length: int):
    """Zwraca komunikat błędu albo None, jeśli hasło jest akceptowalne."""
    if len(password or "") < min_length:
        return f"Hasło musi mieć co najmniej {min_length} znaków."
    if password.lower() in WEAK_PASSWORDS:
        return "To hasło jest zbyt popularne — wybierz inne."
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

    # Za reverse proxy (nginx/Caddy/ngrok...) — zaufaj nagłówkom X-Forwarded-* dokładnie
    # tyle razy, ile proxy stoi przed aplikacją. Przy 0 nagłówki są ignorowane.
    proxy_count = app.config["PROXY_COUNT"]
    if proxy_count > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=proxy_count, x_proto=proxy_count, x_host=proxy_count, x_prefix=0
        )

    logging.basicConfig(
        level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app.logger.setLevel(app.config["LOG_LEVEL"])

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
    def set_security_headers(response):
        # Przeglądarka nie będzie "zgadywać" typu pliku inaczej niż wg Content-Type —
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

        # Strony HTML (zwłaszcza panel) nie powinny być współdzielone w cache pośredników —
        # zawierają nonce, token CSRF i dane zależne od zalogowanego użytkownika.
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "private, no-store"
        return response

    # ---------- loader dla Flask-Login ----------
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ---------- widoki publiczne ----------
    @app.route("/")
    def index():
        query = request.args.get("q", "").strip()
        tag_slug = request.args.get("tag", "").strip()
        recipes_query = Recipe.query.filter_by(status="published").order_by(Recipe.created_at.desc())
        if query:
            recipes_query = recipes_query.filter(Recipe.title.ilike(f"%{_escape_like(query)}%", escape="\\"))
        active_tag = None
        if tag_slug:
            active_tag = Tag.query.filter_by(slug=tag_slug).first()
            if active_tag:
                recipes_query = recipes_query.filter(Recipe.tags.contains(active_tag))
        recipes = recipes_query.all()
        all_tags = Tag.query.order_by(Tag.name).all()
        return render_template(
            "index.html", recipes=recipes, query=query, all_tags=all_tags, active_tag=active_tag
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
        return render_template("recipe_detail.html", recipe=recipe)

    # ---------- logowanie ----------
    def _post_login_redirect_endpoint():
        return "admin_dashboard" if current_user.is_admin else "redaktor_dashboard"

    # Jeden komunikat dla WSZYSTKICH niepowodzeń (zły login, złe hasło, konto zablokowane) —
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
                    current_user.set_password(new_password)
                    db.session.commit()
                    app.logger.info("Użytkownik %r zmienił własne hasło", current_user.username)
                    flash("Hasło zostało zmienione.", "success")
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
        return render_template(
            "admin/dashboard.html",
            recipes=recipes,
            pending_count=pending_count,
            blog_pending_count=blog_pending_count,
        )

    @app.route("/admin/przepis/nowy", methods=["GET", "POST"])
    @login_required
    @admin_required
    def recipe_create():
        if request.method == "POST":
            recipe = Recipe(author_id=current_user.id, status="published")
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
            form_action=url_for("recipe_create"),
            cancel_url=url_for("admin_dashboard"),
            editor_mode=False,
        )

    @app.route("/admin/przepis/<int:recipe_id>/edytuj", methods=["GET", "POST"])
    @login_required
    @admin_required
    def recipe_edit(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
        if request.method == "POST":
            _save_recipe_form(recipe)
            # Admin zapisujący formularz automatycznie zatwierdza przepis (jeśli czekał w kolejce).
            recipe.status = "published"
            recipe.rejection_reason = None
            db.session.commit()
            flash("Przepis został zaktualizowany i opublikowany.", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template(
            "admin/recipe_form.html",
            recipe=recipe,
            units=INGREDIENT_UNITS,
            pan_shapes=PAN_SHAPES,
            all_tags=Tag.query.order_by(Tag.name).all(),
            form_action=url_for("recipe_edit", recipe_id=recipe.id),
            cancel_url=url_for("admin_dashboard"),
            editor_mode=False,
        )

    @app.route("/admin/przepis/<int:recipe_id>/usun", methods=["POST"])
    @login_required
    @admin_required
    def recipe_delete(recipe_id):
        recipe = db.session.get(Recipe, recipe_id) or abort(404)
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
        recipe.status = "published"
        recipe.rejection_reason = None
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
        db.session.commit()
        flash(f"Przepis „{recipe.title}” został odrzucony.", "success")
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
            # Reset hasła odblokowuje też konto — redaktor mógł je stracić przez
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
        if request.method == "POST":
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
        if request.method == "POST":
            _save_recipe_form(recipe)
            # Każda zmiana redaktora (nawet w już opublikowanym przepisie) wraca do kolejki
            # zatwierdzania — administrator musi ponownie potwierdzić treść.
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
        if recipe.status == "published" and not current_user.is_admin:
            flash("Opublikowany przepis może usunąć tylko administrator.", "error")
            return redirect(url_for("redaktor_dashboard"))
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
        return render_template("blog/detail.html", post=post)

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
                post.publish()
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
        db.session.delete(post)
        db.session.commit()
        flash("Wpis został usunięty.", "success")
        return redirect(url_for("admin_blog"))

    @app.route("/admin/blog/<int:post_id>/zatwierdz", methods=["POST"])
    @login_required
    @admin_required
    def blog_approve(post_id):
        post = db.session.get(BlogPost, post_id) or abort(404)
        post.publish()
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
        db.session.commit()
        flash(f"Wpis „{post.title}” został odrzucony.", "success")
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
            if _save_blog_form(post):
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
        if post.status == "published" and not current_user.is_admin:
            flash("Opublikowany wpis może usunąć tylko administrator.", "error")
            return redirect(url_for("redaktor_dashboard"))
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
        # z formularza — pokazujemy je ponownie, żeby autor nie stracił tekstu.
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
        brakuje wymaganych pól — wtedy wywołujący nie zapisuje zmian."""
        title = request.form.get("title", "").strip()[:150]
        content = request.form.get("content", "").strip()
        post.title = title
        post.excerpt = request.form.get("excerpt", "").strip()[:300] or None
        post.content = content
        if not title or not content:
            flash("Podaj tytuł i treść wpisu.", "error")
            return False

        with db.session.no_autoflush:
            base_slug = slugify(title) or "wpis"
            if post.slug != base_slug:
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
                    flash("Archiwum jest zbyt duże po rozpakowaniu — import odrzucony.", "error")
                    return redirect(url_for("backup_page"))

                with zf.open("recipes.json") as fh:
                    manifest = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                if not isinstance(manifest, dict) or not isinstance(manifest.get("recipes", []), list):
                    flash("Plik recipes.json ma nieprawidłową strukturę.", "error")
                    return redirect(url_for("backup_page"))

                if mode == "wipe":
                    # Czyścimy najpierw tabelę pośredniczącą (SQLAlchemy nie robi tego
                    # automatycznie przy masowym Query.delete()), potem przepisy i tagi.
                    db.session.execute(recipe_tags.delete())
                    Recipe.query.delete()
                    Tag.query.delete()

                image_name_map = _extract_backup_images(zf)

                created = updated = 0
                skipped = []
                for entry in manifest.get("recipes", []):
                    recipe, note = _restore_recipe_from_backup(entry, mode, image_name_map)
                    if recipe is None:
                        skipped.append(note)
                    elif note.startswith("utworzono"):
                        created += 1
                    else:
                        updated += 1

                db.session.commit()

            app.logger.info(
                "Admin %r zaimportował kopię zapasową (tryb=%s, utworzono=%s, zaktualizowano=%s)",
                current_user.username, mode, created, updated,
            )
            summary = f"Import zakończony: utworzono {created}, zaktualizowano {updated} przepisów."
            if skipped:
                summary += f" Pominięto {len(skipped)} pozycji."
            flash(summary, "success")
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            db.session.rollback()
            flash(f"Nie udało się odczytać kopii zapasowej — nieprawidłowy plik ({exc}).", "error")

        return redirect(url_for("backup_page"))

    def _sanitize_and_save_image(file_bytes: bytes):
        """
        Weryfikuje, że `file_bytes` to naprawdę obraz w dozwolonym formacie, dekoduje go
        i zapisuje na dysk jako świeżo zakodowany plik pod losową nazwą — zamiast ufać
        rozszerzeniu pliku albo deklarowanemu typowi MIME (oba może sfałszować atakujący).

        Dzięki pełnemu zdekodowaniu i ponownemu zapisaniu obrazu:
        - odrzucamy pliki, które nie są prawidłowymi obrazami (np. przemianowany
          skrypt, plik-polyglot łączący obraz z HTML/JS, uszkodzony plik),
        - usuwamy wszelkie metadane EXIF (mogą zawierać dane lokalizacji GPS,
          model urządzenia itp. — ryzyko prywatności autora zdjęcia),
        - usuwamy dowolne dane doklejone do pliku poza właściwą treścią obrazu,
        - chronimy przed „bombami dekompresji" (plik deklarujący miliardy pikseli) —
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
            return None, "Obraz jest zbyt duży (zbyt wiele pikseli) — odrzucono ze względów bezpieczeństwa."
        except (UnidentifiedImageError, OSError, ValueError):
            return None, "Plik nie jest prawidłowym obrazem (dozwolone: PNG, JPG, GIF, WEBP)."

        detected_format = (image.format or "").upper()
        if detected_format not in SAFE_IMAGE_FORMATS:
            return None, "Niedozwolony format obrazka. Dozwolone: PNG, JPG, GIF, WEBP."

        # Ograniczamy maksymalny wymiar — zmniejszamy proporcjonalnie, jeśli trzeba.
        max_dim = app.config["MAX_IMAGE_DIMENSION"]
        if image.width > max_dim or image.height > max_dim:
            image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        save_format = detected_format
        save_kwargs = {}
        if save_format == "JPEG":
            # JPEG nie obsługuje kanału alfa/palety — konwertujemy do RGB.
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            save_kwargs["quality"] = 88

        ext = SAFE_IMAGE_FORMATS[save_format]
        filename = f"{uuid.uuid4().hex}.{ext}"
        target_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        try:
            # Zapis BEZ przekazywania oryginalnych metadanych (brak exif=...) —
            # to jawnie usuwa EXIF i wszystko poza samą siatką pikseli obrazu.
            image.save(target_path, format=save_format, **save_kwargs)
        except OSError as exc:
            return None, f"Nie udało się zapisać obrazu: {exc}"

        return filename, None

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
                        # Pełna struktura z podziałem na sekcje (np. "Ciasto"/"Krem") — używana
                        # przy imporcie w tej i nowszych wersjach aplikacji.
                        "ingredients_sections": recipe.ingredients_sections,
                        "instructions": recipe.instructions_list,
                        "servings": recipe.servings,
                        "pan_shape": recipe.pan_shape,
                        "pan_size_cm": recipe.pan_size_cm,
                        "pan_width_cm": recipe.pan_width_cm,
                        "pan_length_cm": recipe.pan_length_cm,
                        "tags": [tag.name for tag in recipe.tags],
                        "image_filename": image_filename,
                        "status": recipe.status,
                        "rejection_reason": recipe.rejection_reason,
                        "author_username": recipe.author.username if recipe.author else None,
                        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
                        "updated_at": recipe.updated_at.isoformat() if recipe.updated_at else None,
                    }
                )

            manifest = {
                "app": "wielka-ksiega-przepisow",
                "format_version": 1,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "recipe_count": len(recipes_data),
                "recipes": recipes_data,
            }
            zf.writestr("recipes.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        buffer.seek(0)
        return buffer

    # ---------- kopia zapasowa: rozpakowywanie zdjęć z importu ----------
    def _extract_backup_images(zf: zipfile.ZipFile) -> dict:
        """Sanityzuje i zapisuje na dysk zdjęcia z archiwum (pod nowymi, losowymi nazwami).
        Zawartość ZIP-a traktujemy jako dane niezaufane — każdy plik przechodzi przez
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
                # Pomijamy pojedyncze uszkodzone/nieprawidłowe zdjęcie — nie przerywamy
                # całego importu z powodu jednego złego pliku w archiwum.
                continue
            name_map[original_name] = filename
        return name_map

    # ---------- kopia zapasowa: odtwarzanie pojedynczego przepisu ----------
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
                recipe = Recipe(slug=slug, author_id=current_user.id)
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

            servings = data.get("servings")
            recipe.servings = int(servings) if isinstance(servings, (int, float)) else None

            pan_shape = data.get("pan_shape")
            recipe.pan_shape = pan_shape if pan_shape in PAN_SHAPES else None
            recipe.pan_size_cm = (
                int(data["pan_size_cm"])
                if recipe.pan_shape == "okragla" and isinstance(data.get("pan_size_cm"), (int, float))
                else None
            )
            recipe.pan_width_cm = (
                int(data["pan_width_cm"])
                if recipe.pan_shape == "prostokatna" and isinstance(data.get("pan_width_cm"), (int, float))
                else None
            )
            recipe.pan_length_cm = (
                int(data["pan_length_cm"])
                if recipe.pan_shape == "prostokatna" and isinstance(data.get("pan_length_cm"), (int, float))
                else None
            )

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
                tags.append(tag)
            recipe.tags = tags

            status = data.get("status")
            recipe.status = status if status in RECIPE_STATUSES else "published"
            recipe.rejection_reason = str(data.get("rejection_reason") or "").strip() or None

            # Zdjęcie podmieniamy tylko, jeśli archiwum je zawierało; w przeciwnym razie
            # zostawiamy dotychczasowe (przy aktualizacji) albo brak zdjęcia (przy nowym).
            original_image_name = data.get("image_filename")
            if original_image_name and original_image_name in image_name_map:
                recipe.image_url = url_for(
                    "static", filename=f"uploads/{image_name_map[original_image_name]}"
                )

        return recipe, f"{note_prefix}: „{recipe.title}”"

    def _build_ingredients_text():
        """
        Buduje tekst składników do zapisania w bazie. Preferuje ustrukturyzowane pole
        `ingredients_structured` (JSON zbudowany przez JS tuż przed wysłaniem formularza —
        pozwala przeplatać nagłówki sekcji ze zwykłymi składnikami w dowolnej kolejności).
        Jeśli go brak (np. JS wyłączony), spada do starych, płaskich pól name[]/amount[]/unit[]
        bez podziału na sekcje — formularz nadal da się wypełnić.
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

        return serialize_ingredient_entries(entries)

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
            tags.append(tag)
        recipe.tags = tags

    def _save_recipe_form(recipe: Recipe):
        title = request.form.get("title", "").strip()
        recipe.title = title

        # Wszelkie zapytania do bazy w trakcie wypełniania formularza (sprawdzanie unikalności
        # sluga, wyszukiwanie/tworzenie tagów) mogłyby wywołać przedwczesny autoflush sesji,
        # zanim przepis ma komplet wymaganych pól — stąd blok no_autoflush.
        with db.session.no_autoflush:
            # Slug generujemy tylko jeśli tytuł się zmienił / to nowy przepis
            base_slug = slugify(title) or "przepis"
            if recipe.slug != base_slug:
                candidate = base_slug
                counter = 2
                while Recipe.query.filter(
                    Recipe.slug == candidate, Recipe.id != (recipe.id or -1)
                ).first():
                    candidate = f"{base_slug}-{counter}"
                    counter += 1
                recipe.slug = candidate

            recipe.description = request.form.get("description", "").strip()
            recipe.ingredients = _build_ingredients_text()
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
            recipe.pan_size_cm = int(pan_size) if pan_size.isdigit() else None
            recipe.pan_width_cm = None
            recipe.pan_length_cm = None
        elif recipe.pan_shape == "prostokatna":
            pan_width = request.form.get("pan_width_cm", "").strip()
            pan_length = request.form.get("pan_length_cm", "").strip()
            recipe.pan_width_cm = int(pan_width) if pan_width.isdigit() else None
            recipe.pan_length_cm = int(pan_length) if pan_length.isdigit() else None
            recipe.pan_size_cm = None
        else:
            recipe.pan_size_cm = None
            recipe.pan_width_cm = None
            recipe.pan_length_cm = None

        servings = request.form.get("servings", "").strip()
        recipe.servings = int(servings) if servings.isdigit() else None

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

    @app.cli.command("export-backup")
    @click.option("--output", "-o", required=True, type=click.Path(dir_okay=False, writable=True),
                  help="Ścieżka pliku .zip do zapisania (dla cron: np. /backups/przepisy-$(date +%F).zip).")
    def export_backup(output):
        """Zapisuje kopię zapasową (przepisy + zdjęcia) bez logowania w przeglądarce — do zadań cron."""
        buffer = _build_backup_zip()
        with open(output, "wb") as fh:
            fh.write(buffer.getvalue())
        os.chmod(output, 0o600)  # kopia zawiera całą treść serwisu
        click.echo(f"Zapisano kopię zapasową: {output} ({os.path.getsize(output)} B)")

    return app


if __name__ == "__main__":
    # Wygodne uruchomienie lokalne: APP_ENV=development python app.py
    # Na produkcji NIE używaj tego — uruchamiaj gunicorna (patrz wsgi.py / DEPLOYMENT.md).
    _dev_app = create_app()
    if _dev_app.config["APP_ENV"] != "development":
        raise SystemExit("Serwer deweloperski działa tylko przy APP_ENV=development. Na produkcji użyj gunicorna.")
    _dev_app.run(debug=True)
