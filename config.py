"""
Konfiguracja aplikacji.

Zasada: domyślnie aplikacja działa w trybie PRODUKCYJNYM (najbezpieczniejsze ustawienia)
i odmawia startu, jeśli brakuje wymaganych sekretów. Do pracy lokalnej ustaw
`APP_ENV=development` (patrz .env.example).
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Wczytuje plik .env (jeśli istnieje). Zmienne już ustawione w środowisku mają pierwszeństwo.
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"Zmienna środowiskowa {name} musi być liczbą całkowitą, a jest: {value!r}")


APP_ENV = os.environ.get("APP_ENV", "production").strip().lower()

# Wartości, których nigdy nie wolno użyć jako SECRET_KEY na produkcji.
INSECURE_SECRET_KEYS = {
    "zmien-ten-klucz-na-produkcji",
    "dev-only-insecure-key",
    "changeme",
    "secret",
    "",
}


class Config:
    """Konfiguracja produkcyjna (domyślna)."""

    APP_ENV = "production"

    # Wymagany na produkcji (min. 32 znaki) - wygeneruj: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'recipes.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Zdjęcia muszą leżeć w katalogu static/, bo serwowane są jako /static/uploads/...
    UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads")
    MAX_CONTENT_LENGTH = _env_int("MAX_UPLOAD_MB", 8) * 1024 * 1024  # limit rozmiaru żądania
    MAX_IMAGE_DIMENSION = 4000  # px - większe obrazy są proporcjonalnie zmniejszane

    # Limity importu kopii zapasowej (ochrona przed „bombą ZIP").
    BACKUP_MAX_UNCOMPRESSED_MB = _env_int("BACKUP_MAX_UNCOMPRESSED_MB", 300)
    BACKUP_MAX_ENTRIES = 5000

    # ---- Logowanie / hasła ----
    MIN_PASSWORD_LENGTH = 10
    LOGIN_MAX_ATTEMPTS = _env_int("LOGIN_MAX_ATTEMPTS", 5)  # tyle błędów z rzędu blokuje konto
    LOGIN_LOCKOUT_MINUTES = _env_int("LOGIN_LOCKOUT_MINUTES", 15)
    LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "10 per minute;30 per hour")  # per adres IP
    # Magazyn liczników limitów. "memory://" działa tylko dla jednego procesu;
    # przy kilku workerach użyj współdzielonego, np. redis://redis:6379/0
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    # Limity dla czytelników (per adres IP): dodawanie komentarzy i ocen.
    COMMENT_RATE_LIMIT = os.environ.get("COMMENT_RATE_LIMIT", "5 per 10 minutes;20 per day")
    RATING_RATE_LIMIT = os.environ.get("RATING_RATE_LIMIT", "20 per hour")
    RATELIMIT_HEADERS_ENABLED = False

    # ---- Sesja i ciasteczka ----
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)  # produkcja = tylko HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_env_int("SESSION_LIFETIME_HOURS", 12))
    PREFERRED_URL_SCHEME = "https"
    WTF_CSRF_TIME_LIMIT = None  # token ważny tak długo jak sesja (długie edytowanie przepisu)

    # ---- Za reverse proxy (nginx, Caddy, Cloudflare Tunnel, ngrok) ----
    # Ile serwerów proxy stoi przed aplikacją. 0 = brak (aplikacja wystawiona bezpośrednio).
    # Ustaw poprawnie: od tego zależy m.in. limit prób logowania per IP i wykrywanie HTTPS.
    PROXY_COUNT = _env_int("PROXY_COUNT", 0)
    HSTS_SECONDS = _env_int("HSTS_SECONDS", 31536000)  # wysyłane tylko przez HTTPS

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    # ---- Polityka prywatności ----
    # Administrator danych (imię i nazwisko / firma, adres) oraz e-mail kontaktowy w sprawach
    # danych osobowych - wyświetlane na stronie /polityka-prywatnosci. Ustaw na produkcji.
    PRIVACY_CONTROLLER = os.environ.get("PRIVACY_CONTROLLER", "").strip()
    PRIVACY_CONTACT_EMAIL = os.environ.get("PRIVACY_CONTACT_EMAIL", "").strip()


class DevelopmentConfig(Config):
    APP_ENV = "development"
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-key"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    PREFERRED_URL_SCHEME = "http"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()


class TestingConfig(Config):
    APP_ENV = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key-only-for-automated-tests-0123456789"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SESSION_COOKIE_SECURE = False
    PREFERRED_URL_SCHEME = "http"
    RATELIMIT_ENABLED = False
    LOG_LEVEL = "WARNING"


_CONFIGS = {
    "production": Config,
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "testing": TestingConfig,
}


def get_config():
    try:
        return _CONFIGS[APP_ENV]
    except KeyError:
        raise RuntimeError(
            f"Nieznana wartość APP_ENV={APP_ENV!r}. Dozwolone: production, development."
        )


def validate_production_config(config: dict) -> None:
    """Zatrzymuje start aplikacji produkcyjnej, jeśli konfiguracja jest niebezpieczna."""
    if config.get("APP_ENV") != "production":
        return

    problems = []
    key = config.get("SECRET_KEY") or ""
    if key.lower() in INSECURE_SECRET_KEYS or len(key) < 32:
        problems.append(
            "SECRET_KEY jest nieustawiony, zbyt krótki (min. 32 znaki) lub domyślny. "
            'Wygeneruj: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    if problems:
        raise RuntimeError(
            "Odmowa startu - niebezpieczna konfiguracja produkcyjna:\n  - "
            + "\n  - ".join(problems)
            + "\n(Do pracy lokalnej ustaw APP_ENV=development.)"
        )
