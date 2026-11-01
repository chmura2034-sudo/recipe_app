# Wielka Księga Przepisów (Flask)

Prosta aplikacja webowa do publikowania przepisów kulinarnych.
Każdy odwiedzający może przeglądać i wyszukiwać przepisy. Treść dodają **administrator**
(od razu publicznie) oraz **redaktorzy** (ich przepisy czekają na zatwierdzenie —
patrz sekcja „Role” niżej).

## Funkcje

- Lista przepisów + wyszukiwarka po tytule i filtrowanie po tagach
- Strona szczegółów przepisu (składniki, kroki z checklistą wykonania, forma, porcje)
- Przeliczanie przepisu wg liczby porcji lub wielkości/kształtu formy (okrągła ↔ kwadratowa/prostokątna)
- **Dwie role kont**: administrator (pełne prawa) i redaktor (może dodawać/edytować
  własne przepisy, ale wymagają one zatwierdzenia przez administratora — patrz sekcja niżej)
- Panel administratora z pełnym CRUD-em przepisów (zdjęcia, tagi, dynamiczne składniki i kroki)
- **Sekcje składników** — listę składników można podzielić na sekcje o dowolnych nazwach
  (np. „Ciasto”, „Krem”): w formularzu przycisk „+ Dodaj sekcję”, kolejność zmienia się
  przyciskami ▲▼; na stronie przepisu składniki są pogrupowane pod nagłówkami, a przeliczanie
  porcji/formy obejmuje wszystkie sekcje
- Kopia zapasowa — eksport wszystkich przepisów i zdjęć do archiwum ZIP oraz import
  (3 tryby: uzupełnij i zaktualizuj / dodaj tylko nowe / zastąp wszystko)
- Ochrona CSRF na wszystkich formularzach (Flask-WTF)
- Migracje schematu bazy przez Flask-Migrate/Alembic (`flask db upgrade`)
- Gotowe do wdrożenia produkcyjnego: gunicorn, Docker, przykłady nginx/systemd — patrz
  sekcja „Wdrożenie produkcyjne” niżej

## Instalacja (praca lokalna)

```bash
# 1. Utwórz i aktywuj wirtualne środowisko
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Zainstaluj zależności
pip install -r requirements.txt

# 3. Skopiuj przykładową konfigurację i włącz tryb deweloperski
cp .env.example .env
# w .env ustaw: APP_ENV=development
# (tryb development nie wymaga SECRET_KEY i działa po zwykłym http://;
#  bez tego aplikacja domyślnie startuje w trybie PRODUCTION i odmówi
#  uruchomienia bez poprawnego SECRET_KEY — patrz sekcja "Bezpieczeństwo")

export FLASK_APP=app.py         # Windows (PowerShell): $env:FLASK_APP="app.py"

# 4. Utwórz schemat bazy danych (migracje, nie db.create_all())
flask db upgrade

# 5. Utwórz konto administratora
flask create-admin --username admin --password twoje-bezpieczne-haslo

# 6. Uruchom serwer deweloperski
flask run
```

Aplikacja będzie dostępna pod adresem `http://127.0.0.1:5000`.

Serwer wbudowany we Flaska (`flask run` / `python app.py`) jest tylko do pracy lokalnej —
jednowątkowy, bez obsługi wielu równoczesnych połączeń. Do wdrożenia patrz sekcja
„Wdrożenie produkcyjne” niżej.

## Zmienne środowiskowe

Pełna, opisana lista jest w pliku `.env.example` (skopiuj do `.env` — plik ten nie trafia
do repozytorium, patrz `.gitignore`). Najważniejsze:

| Zmienna                  | Opis                                                                 | Domyślnie (production) |
|---------------------------|-----------------------------------------------------------------------|--------------------------|
| `APP_ENV`                 | `production` (bezpieczne, wymaga sekretów) albo `development`        | `production`             |
| `SECRET_KEY`               | Klucz sesji/CSRF. **Wymagany** na produkcji, min. 32 znaki            | *(brak — aplikacja nie wystartuje)* |
| `DATABASE_URL`             | Connection string bazy danych                                        | plik SQLite `recipes.db` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Domyślne dane dla `flask create-admin` (bez podania opcji)   | —                         |
| `PROXY_COUNT`              | Liczba serwerów proxy PRZED aplikacją (nginx, Cloudflare Tunnel...)   | `0`                       |
| `SESSION_COOKIE_SECURE`    | Ciasteczko sesji tylko po HTTPS                                       | `true`                    |
| `RATELIMIT_STORAGE_URI`    | Magazyn liczników limitu logowań — `redis://...` przy kilku workerach | `memory://` (1 proces)    |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | Próg i czas blokady konta po nieudanych logowaniach | `5` / `15`                |
| `MAX_UPLOAD_MB`            | Limit rozmiaru przesyłanego pliku (zdjęcia)                            | `8`                       |
| `BACKUP_MAX_UNCOMPRESSED_MB` | Limit rozpakowanego rozmiaru importowanej kopii zapasowej            | `300`                     |

## Struktura projektu

```
recipe_app/
├── app.py                     # trasy, logika, komendy CLI
├── config.py                   # konfiguracja (production / development / testing)
├── models.py                    # modele: User, Recipe, Tag (SQLAlchemy)
├── wsgi.py                       # punkt wejścia dla gunicorna
├── requirements.txt
├── .env.example                  # szablon zmiennych środowiskowych (skopiuj do .env)
├── .gitignore
├── Dockerfile
├── docker-compose.yml.example
├── deploy/
│   ├── nginx.conf.example        # reverse proxy + HTTPS
│   └── recipe-app.service.example # jednostka systemd (gunicorn)
├── migrations/                   # migracje Alembic (flask db upgrade)
│   └── versions/
├── static/
│   ├── style.css
│   ├── js/app.js                 # wspólne zachowania UI (data-confirm, data-toggle-target)
│   └── uploads/                  # przesłane zdjęcia (poza repozytorium, patrz .gitignore)
└── templates/
    ├── base.html
    ├── index.html
    ├── recipe_detail.html
    ├── login.html
    ├── errors.html
    ├── admin/
    │   ├── dashboard.html
    │   ├── recipe_form.html
    │   ├── queue.html             # kolejka zatwierdzania
    │   ├── editors.html           # zarządzanie kontami redaktorów
    │   └── backup.html
    └── redaktor/
        └── dashboard.html
```

## Role: administrator i redaktor

- **Administrator** — pełne prawa: dodaje, edytuje i usuwa dowolny przepis; przepisy dodane
  lub zaakceptowane przez admina są od razu publiczne.
- **Redaktor** — może tworzyć własne przepisy i je edytować, ale każda nowa treść
  (nowy przepis albo zmiana w już opublikowanym) trafia do **kolejki zatwierdzania**
  (`/admin/kolejka`) i staje się publicznie widoczna dopiero, gdy administrator ją zaakceptuje.
  Administrator może też odrzucić przepis z podaniem powodu — redaktor zobaczy go
  na swoim koncie (`/redakcja`) i może poprawić przepis, co wysyła go ponownie do zatwierdzenia.

Konta redaktorów zakłada administrator — nie ma samodzielnej rejestracji. Można to zrobić
z poziomu panelu (`/admin/redaktorzy`) albo z linii poleceń:

```bash
flask create-redaktor --username jan.kowalski --password bezpieczne-haslo
```

## Kopia zapasowa przepisów

_Sekcje składników są zapisywane w kopii zapasowej (pole `ingredients_sections` w `recipes.json`)
i odtwarzane przy imporcie; starsze kopie bez tego pola importują się jako zwykła, płaska lista._

Panel administratora (`/admin/kopia-zapasowa`) pozwala:

- **Eksportować** wszystkie przepisy do jednego pliku `.zip` zawierającego `recipes.json`
  (tytuły, składniki, kroki, tagi, forma, porcje) oraz folder `images/` ze zdjęciami potraw.
  Ten format jest przenośny i niezależny od silnika bazy danych — działa niezależnie od tego,
  czy używasz SQLite czy np. PostgreSQL przez `DATABASE_URL`.
- **Importować** wcześniej pobrane archiwum w jednym z trzech trybów:
  - *Uzupełnij i zaktualizuj* — dopasowuje przepisy po tytule/slugu; istniejące nadpisuje danymi z kopii
  - *Dodaj tylko nowe* — pomija przepisy, które już są w bazie
  - *Zastąp wszystko* — usuwa wszystkie obecne przepisy i tagi, potem importuje od zera (nieodwracalne)

### Zalecana praktyka

Regularnie pobieraj kopię zapasową i trzymaj ją **poza serwerem** (dysk w chmurze, backup lokalny).
Z poziomu przeglądarki służy do tego przycisk na `/admin/kopia-zapasowa`; do automatyzacji
(np. przez `cron`) użyj polecenia `flask export-backup` — patrz sekcja „Wdrożenie produkcyjne”.

Uwaga: import nie usuwa automatycznie plików zdjęć osieroconych po trybie „Zastąp wszystko”
(stare pliki zostają na dysku w `static/uploads/`, ale nie są już z niczym powiązane) —
to świadome uproszczenie, które nie wpływa na poprawność działania aplikacji.

## Migracje bazy danych

Schemat bazy tworzą i aktualizują migracje Alembic (Flask-Migrate) — **nie** `db.create_all()`.
Aktualny schemat (role użytkowników, kolejka zatwierdzania, blokada logowania, tagi, sekcje
składników itd.) jest w całości opisany w `migrations/versions/`.

```bash
flask db upgrade          # tworzy/aktualizuje schemat do najnowszej wersji
flask db current           # pokazuje, na której wersji jest baza
flask db history            # pełna historia migracji
```

Po zmianie modeli (`models.py`) w kolejnych wersjach projektu wygeneruj nową migrację:

```bash
flask db migrate -m "opis zmiany"   # generuje plik w migrations/versions/
flask db upgrade                     # stosuje go do bazy
```

Zawsze **przejrzyj** wygenerowany plik przed uruchomieniem — Alembic dobrze radzi sobie
z nowymi kolumnami, ale np. zmiany wymagające wypełnienia danych albo przenoszenia wartości
między kolumnami trzeba dopisać ręcznie.

## Bezpieczeństwo

Aplikacja zawiera kilka wbudowanych zabezpieczeń:

- **SQL injection** — wszystkie zapytania do bazy idą przez ORM SQLAlchemy
  (`Recipe.query.filter(...)`, `.filter_by(...)`, `.ilike(...)` itd.), które zawsze wiąże
  wartości jako parametry, nigdy nie buduje zapytań przez sklejanie surowych stringów SQL.
  W kodzie nie ma ani jednego wywołania `db.session.execute(text(f"..."))` z wartością
  użytkownika wklejoną bezpośrednio w zapytanie.
- **XSS (Cross-Site Scripting)** — Jinja2 domyślnie escapuje wszystko, co wypisujesz przez
  `{{ ... }}` (tytuły, opisy, składniki, tagi, komentarze administratora itd.); w żadnym
  szablonie nie użyto filtra `|safe` ani `{% autoescape false %}`, które mogłyby to wyłączyć.
  Dodatkowo `Content-Security-Policy` na każdej odpowiedzi dopuszcza skrypty wyłącznie
  z własnej domeny (`script-src 'self' 'nonce-...'`, losowy nonce inny dla każdego żądania) —
  bez `'unsafe-inline'`, więc wstrzyknięty przez atak `<script>` albo `onclick="..."`
  nie wykona się nawet, gdyby autoescaping zawiódł. W szablonach nie ma ani jednego
  inline'owego `onclick=`/`onsubmit=` — zamiast tego mały, wspólny plik
  `static/js/app.js` obsługuje potwierdzenia usuwania (`data-confirm="..."`) i
  rozwijanie/zwijanie elementów (`data-toggle-target="..."`) na podstawie atrybutów
  `data-*`, czyli danych, a nie kodu.
- **Bezpieczne przekierowania po logowaniu** — parametr `?next=` jest sprawdzany
  (`is_safe_redirect_target` w `app.py`) i akceptowany tylko, gdy wskazuje na ścieżkę
  wewnątrz tej samej aplikacji; próba przekierowania na obcą domenę (`https://zla-strona.pl`)
  albo adres protokołowo-względny (`//zla-strona.pl`) jest odrzucana — chroni to przed
  wykorzystaniem linku do logowania jako narzędzia phishingu.
- **Ochrona przed atakiem czasowym (timing attack) i wyliczaniem kont** — logowanie na
  nieistniejące konto wykonuje dokładnie tak samo kosztowne, fikcyjne sprawdzenie hasła
  (`_DUMMY_PASSWORD_HASH`) jak logowanie na istniejące konto ze złym hasłem, więc czas
  odpowiedzi serwera nie zdradza, czy dana nazwa użytkownika w ogóle istnieje w bazie.
  Komunikat błędu jest identyczny we wszystkich przypadkach (zły login, złe hasło,
  zablokowane konto).
- **Wylogowanie tylko przez POST** (z tokenem CSRF) — obca strona nie może wylogować
  użytkownika samym linkiem czy obrazkiem (`<img src="/logout">`); GET na `/logout`
  zwraca teraz 405.
- **Za reverse proxy** (`PROXY_COUNT` w `.env`) — nagłówki `X-Forwarded-For`/`X-Forwarded-Proto`
  są zaufane tylko wtedy, gdy faktycznie skonfigurowano tyle serwerów proxy przed aplikacją.
  Przy `PROXY_COUNT=0` (domyślnie) są całkowicie ignorowane — inaczej ktokolwiek mógłby
  wysłać własny nagłówek `X-Forwarded-For` i podszyć się pod inny adres IP, omijając
  limit prób logowania per IP.
- **Import kopii zapasowej odporny na „zip bombę”** — przed rozpakowaniem sprawdzana jest
  liczba wpisów w archiwum i łączny rozmiar po rozpakowaniu (`BACKUP_MAX_ENTRIES`,
  `BACKUP_MAX_UNCOMPRESSED_MB`); archiwum przekraczające limity jest odrzucane, zanim
  cokolwiek trafi na dysk.
- **Silne hasła wymuszone także w CLI** — `flask create-admin` / `flask create-redaktor`
  i tworzenie redaktora z panelu administratora odrzucają hasła krótsze niż
  `MIN_PASSWORD_LENGTH` (domyślnie 10 znaków) oraz z listy popularnych, słabych haseł
  (`WEAK_PASSWORDS` w `app.py`).
- **Sanityzacja przesyłanych zdjęć** — każdy wgrywany albo wklejany obrazek (a także
  zdjęcia z importowanej kopii zapasowej) jest w całości dekodowany i **ponownie zapisywany
  od zera przez Pillow** (`_sanitize_and_save_image` w `app.py`), zamiast ufać rozszerzeniu
  pliku czy deklarowanemu typowi MIME. Dzięki temu:
  - odrzucane są pliki, które nie są prawdziwymi obrazami (np. przemianowany skrypt,
    plik-polyglot łączący obraz z HTML/JS, uszkodzony/spreparowany plik),
  - usuwane są metadane EXIF (mogą zawierać lokalizację GPS, model urządzenia itp.),
  - usuwane są wszelkie dane doklejone do pliku poza właściwą treścią obrazu,
  - obrazy o podejrzanie dużej liczbie pikseli („bomby dekompresji”) są odrzucane,
    a zwykłe duże zdjęcia proporcjonalnie zmniejszane (`MAX_IMAGE_DIMENSION` w `config.py`),
  - plik zapisywany jest pod nową, losową nazwą (UUID) — nazwa nadana przez użytkownika
    nigdy nie trafia na dysk ani do adresu URL.
  Limit rozmiaru przesyłanego pliku (`MAX_CONTENT_LENGTH`, domyślnie 8 MB) chroni dodatkowo
  przed zapychaniem serwera bardzo dużymi plikami.
- **Limit prób logowania** — dwie niezależne warstwy ochrony przed atakiem brute-force:
  - limit na poziomie adresu IP przez Flask-Limiter (`LOGIN_RATE_LIMIT` w `config.py`,
    domyślnie 10 prób/minutę i 30/godzinę na jeden adres IP, niezależnie od loginu),
  - blokada konkretnego konta na `LOGIN_LOCKOUT_MINUTES` minut po `LOGIN_MAX_ATTEMPTS`
    nieudanych próbach z rzędu (domyślnie: blokada na 15 minut po 5 próbach) —
    licznik zeruje się po udanym logowaniu.
  Komunikat błędu logowania jest zawsze taki sam niezależnie od tego, czy podana nazwa
  użytkownika w ogóle istnieje w bazie — utrudnia to atakującemu sprawdzanie, które konta
  są zarejestrowane (tzw. ochrona przed username enumeration). Blokada konta to świadomy
  kompromis: ktoś obcy, znając Twój login, może Cię czasowo zablokować, celowo podając
  złe hasło 5 razy — w takiej sytuacji odblokuj konto natychmiast poleceniem
  `flask unlock-user --username nazwa`, bez czekania na upływ `LOGIN_LOCKOUT_MINUTES`.

## Wdrożenie produkcyjne

Projekt zawiera gotowe pliki do dwóch sposobów wdrożenia — wybierz jeden.

### Opcja A: Docker / docker-compose

```bash
cp .env.example .env        # uzupełnij SECRET_KEY (wygeneruj: python -c "import secrets; print(secrets.token_hex(32))")
cp docker-compose.yml.example docker-compose.yml

docker compose run --rm app flask db upgrade
docker compose run --rm app flask create-admin --username admin
docker compose up -d
```

Baza SQLite i przesłane zdjęcia żyją w nazwanych wolumenach Dockera (`db-data`,
`uploads-data`), więc przetrwają rebuild obrazu. `Dockerfile` uruchamia aplikację jako
user bez uprawnień roota i wystawia `/healthz` jako `HEALTHCHECK`.

### Opcja B: gunicorn + nginx + systemd (serwer VPS)

```bash
# Na serwerze, jako zwykły użytkownik z sudo:
sudo mkdir -p /opt/recipe-app && sudo chown $USER /opt/recipe-app
git clone <adres-repozytorium> /opt/recipe-app   # albo skopiuj pliki inaczej
cd /opt/recipe-app

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
# uzupełnij w .env: SECRET_KEY (wygenerowany), ADMIN_USERNAME, DATABASE_URL jeśli nie SQLite, PROXY_COUNT=1

export APP_ENV=production FLASK_APP=app.py
venv/bin/flask db upgrade
venv/bin/flask create-admin --username admin

sudo cp deploy/recipe-app.service.example /etc/systemd/system/recipe-app.service
sudo nano /etc/systemd/system/recipe-app.service   # popraw ścieżki/User zgodnie z komentarzami w pliku
sudo systemctl daemon-reload
sudo systemctl enable --now recipe-app
sudo systemctl status recipe-app

sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/recipe-app
sudo nano /etc/nginx/sites-available/recipe-app   # ustaw domenę, ścieżkę do certyfikatu SSL
sudo ln -s /etc/nginx/sites-available/recipe-app /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`wsgi.py` to punkt wejścia dla gunicorna (`gunicorn wsgi:app`) — patrz komentarz w pliku.
Certyfikat SSL (np. Let's Encrypt/certbot) zakładamy jako już wystawiony przed tym krokiem.

### Kopie zapasowe przez cron (obie opcje)

```bash
# crontab -e, backup codziennie o 3:00 (dostosuj ścieżki do swojego wdrożenia)
0 3 * * * cd /opt/recipe-app && venv/bin/flask export-backup -o /backups/przepisy-$(date +\%F).zip
```

`flask export-backup` działa bez przeglądarki/sesji i zapisuje plik z uprawnieniami `600`
(czytelny tylko dla właściciela) — patrz sekcja „Kopia zapasowa przepisów” wyżej.

### Lista kontrolna przed pierwszym uruchomieniem na produkcji

- [ ] `SECRET_KEY` wygenerowany (`python -c "import secrets; print(secrets.token_hex(32))"`)
      i ustawiony w `.env` — bez tego aplikacja **odmówi startu** (patrz `validate_production_config`).
- [ ] `APP_ENV=production` (domyślne — po prostu nie ustawiaj `development` na serwerze).
- [ ] Aplikacja dostępna wyłącznie przez HTTPS (nginx/Caddy + certyfikat); `SESSION_COOKIE_SECURE`
      zostaje na `true` (domyślne w production).
- [ ] `PROXY_COUNT` ustawiony na dokładną liczbę serwerów proxy przed aplikacją (zwykle `1`
      dla pojedynczego nginx) — źle ustawiony psuje limit logowań per IP i wykrywanie HTTPS.
- [ ] Hasło administratora nadane przy `flask create-admin` jest unikalne i silne
      (min. 10 znaków, nie z listy popularnych — wymuszane automatycznie).
- [ ] Migracje zastosowane (`flask db upgrade`) **przed** pierwszym uruchomieniem gunicorna.
- [ ] Kopie zapasowe skonfigurowane (cron + `flask export-backup`) i trzymane **poza** serwerem.
- [ ] Przy więcej niż jednym workerze gunicorna: `RATELIMIT_STORAGE_URI` wskazuje na Redis,
      nie zostaje na domyślnym `memory://` (inaczej każdy worker liczy próby logowania osobno).
- [ ] `.env` ma uprawnienia `600` i nie trafia do systemu kontroli wersji (już w `.gitignore`).
