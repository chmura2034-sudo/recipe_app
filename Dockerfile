FROM python:3.12-slim

# libjpeg/zlib itp. - potrzebne przez Pillow do dekodowania JPEG/PNG/WEBP
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libwebp7 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Użytkownik bez uprawnień roota (obrona w głąb - nawet przy RCE atakujący nie ma roota w kontenerze).
# /data to miejsce na wolumen z bazą SQLite przy uruchamianiu przez docker-compose.yml.example
# (Docker tworzy zawartość nowego wolumenu z uprawnieniami takimi, jak katalog w obrazie -
# stąd chown tutaj, żeby appuser mógł tam zapisywać).
RUN useradd --create-home --shell /bin/false appuser \
    && mkdir -p static/uploads instance /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

# Migracje uruchamiaj osobno przed startem (patrz docker-compose.yml.example) -
# kontener aplikacji NIE modyfikuje schematu bazy przy starcie.
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
