"""
Punkt wejścia dla serwera produkcyjnego (gunicorn/uwsgi).

Deweloperski `flask run` / `python app.py` używa wbudowanego serwera Flaska —
nie nadaje się do produkcji (jednowątkowy, bez obsługi wielu równoczesnych
połączeń, bez limitów, ostrzeżenie wypisywane przy starcie).

Użycie (patrz też README.md -> "Wdrożenie produkcyjne"):

    gunicorn --workers 4 --bind 0.0.0.0:8000 wsgi:app

`create_app()` bez argumentu czyta konfigurację z APP_ENV (domyślnie "production"
w config.py) i odmówi startu, jeśli brakuje wymaganych zmiennych środowiskowych
takich jak SECRET_KEY — patrz config.validate_production_config().
"""

from app import create_app

app = create_app()
