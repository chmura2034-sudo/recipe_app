# Szczypta Smaku - przepisy i blog kulinarny (Flask)

Prosta aplikacja webowa do publikowania przepisów kulinarnych.
Każdy odwiedzający może przeglądać i wyszukiwać przepisy. Treść dodają **administrator**
(od razu publicznie) oraz **redaktorzy** (ich przepisy czekają na zatwierdzenie -
patrz sekcja „Role” niżej).

## Funkcje

- Lista przepisów + wyszukiwarka po tytule (bez względu na wielkość liter i polskie znaki: `zurek` znajdzie „Żurek”) i filtrowanie po tagach
- Strona szczegółów przepisu (składniki, kroki z checklistą wykonania, forma, porcje)
- Przeliczanie przepisu wg liczby porcji lub wielkości/kształtu formy (okrągła ↔ kwadratowa/prostokątna)
- **Dwie role kont**: administrator (pełne prawa) i redaktor (może dodawać/edytować
  własne przepisy, ale wymagają one zatwierdzenia przez administratora - patrz sekcja niżej)
- Panel administratora z pełnym CRUD-em przepisów (zdjęcia, tagi, dynamiczne składniki i kroki)
- **Sekcje składników** - listę składników można podzielić na sekcje o dowolnych nazwach
  (np. „Ciasto”, „Krem”): w formularzu przycisk „+ Dodaj sekcję”, kolejność zmienia się
  przyciskami ▲▼; na stronie przepisu składniki są pogrupowane pod nagłówkami, a przeliczanie
  porcji/formy obejmuje wszystkie sekcje
- Kopia zapasowa - eksport wszystkich przepisów i zdjęć do archiwum ZIP oraz import
  (3 tryby: uzupełnij i zaktualizuj / dodaj tylko nowe / zastąp wszystko)
- Ochrona CSRF na wszystkich formularzach (Flask-WTF)
- Migracje schematu bazy przez Flask-Migrate/Alembic (`flask db upgrade`)
- Gotowe do wdrożenia produkcyjnego: gunicorn, Docker, przykłady nginx/systemd - patrz
  sekcja „Wdrożenie produkcyjne” niżej

## Instalacja (praca lokalna)

```bash
# 1. Utwórz i aktywuj wirtualne środowisko
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Zainstaluj zależności
pip install -r requirements.txt

# 3. Utwórz plik .env i włącz tryb deweloperski
echo "APP_ENV=development" > .env
# (tryb development nie wymaga SECRET_KEY i działa po zwykłym http://;
#  bez tego aplikacja domyślnie startuje w trybie PRODUCTION i odmówi
#  uruchomienia bez poprawnego SECRET_KEY - patrz sekcja "Bezpieczeństwo")

export FLASK_APP=app.py         # Windows (PowerShell): $env:FLASK_APP="app.py"

# 4. Utwórz schemat bazy danych (migracje, nie db.create_all())
flask db upgrade

# 5. Utwórz konto administratora
flask create-admin --username admin --password twoje-bezpieczne-haslo

# 6. Uruchom serwer deweloperski
flask run
```

Aplikacja będzie dostępna pod adresem `http://127.0.0.1:5000`.

Serwer wbudowany we Flaska (`flask run` / `python app.py`) jest tylko do pracy lokalnej -
jednowątkowy, bez obsługi wielu równoczesnych połączeń. Do wdrożenia patrz sekcja
„Wdrożenie produkcyjne” niżej.

## Zmienne środowiskowe

Aplikacja czyta zmienne ze środowiska oraz z pliku `.env` w katalogu projektu
(`python-dotenv`; zmienne ustawione w środowisku mają pierwszeństwo). Plik `.env` nie trafia
do repozytorium (patrz `.gitignore`). Pełną listę z opisami i wartościami domyślnymi znajdziesz
w `.env.example`. Najważniejsze zmienne:

| Zmienna                  | Opis                                                                 | Domyślnie (production) |
|---------------------------|-----------------------------------------------------------------------|--------------------------|
| `APP_ENV`                 | `production` (bezpieczne, wymaga sekretów) albo `development`        | `production`             |
| `SECRET_KEY`               | Klucz sesji/CSRF. **Wymagany** na produkcji, min. 32 znaki            | *(brak - aplikacja nie wystartuje)* |
| `DATABASE_URL`             | Connection string bazy danych                                        | plik SQLite `recipes.db` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Domyślne dane dla `flask create-admin` (bez podania opcji)   | -                         |
| `PROXY_COUNT`              | Liczba serwerów proxy PRZED aplikacją (nginx, Cloudflare Tunnel...)   | `0`                       |
| `SESSION_COOKIE_SECURE`    | Ciasteczko sesji tylko po HTTPS                                       | `true`                    |
| `RATELIMIT_STORAGE_URI`    | Magazyn liczników limitów (logowanie, komentarze, oceny) - na produkcji `redis://...` | `memory://` (1 proces)    |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | Próg i czas blokady konta po nieudanych logowaniach | `5` / `15`                |
| `MAX_UPLOAD_MB`            | Limit rozmiaru żądania w aplikacji (zdjęcia, import kopii zapasowej)   | `100`                     |
| `BACKUP_MAX_UNCOMPRESSED_MB` | Limit rozpakowanego rozmiaru importowanej kopii zapasowej            | `300`                     |
| `TRUSTED_HOSTS`            | Dozwolone domeny (nagłówek Host), po przecinku; `localhost`/`127.0.0.1` dopisywane zawsze | *(puste - brak sprawdzania, ostrzeżenie w logu)* |
| `PRIVACY_CONTROLLER`       | Administrator danych (imię i nazwisko / firma, adres) na stronie `/polityka-prywatnosci` | *(puste - strona pokazuje „uzupełnij")* |
| `PRIVACY_CONTACT_EMAIL`    | E-mail w sprawach danych osobowych na stronie `/polityka-prywatnosci` | *(puste)*                 |

## Struktura projektu

```
recipe_app/
├── app.py                     # trasy, logika, komendy CLI
├── config.py                   # konfiguracja (production / development / testing)
├── models.py                    # modele: User, Recipe, Tag (SQLAlchemy)
├── wsgi.py                       # punkt wejścia dla gunicorna
├── requirements.txt
├── .env                          # zmienne środowiskowe (tworzysz sam, poza repozytorium)
├── .env.example                  # wzór pliku .env ze wszystkimi zmiennymi
├── .gitignore
├── Dockerfile
├── .dockerignore                 # .env, baza, zdjęcia, venv, .git NIE trafiają do obrazu
├── docker-compose.yml.example
├── deploy/
│   ├── nginx.conf.example        # reverse proxy + HTTPS
│   ├── recipe-app.service.example # jednostka systemd (gunicorn)
│   ├── journald-retention.conf.example # usuwanie logów aplikacji po 30 dniach
│   ├── logrotate-nginx.conf.example    # usuwanie logów nginx po 30 dniach
│   └── wireguard/                # tunel VPS1 (nginx) ↔ VPS2 (aplikacja), opcja C
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

- **Administrator** - pełne prawa: dodaje, edytuje i usuwa dowolny przepis; przepisy dodane
  lub zaakceptowane przez admina są od razu publiczne.
- **Redaktor** - może tworzyć własne przepisy i je edytować, ale każda nowa treść
  (nowy przepis albo zmiana w już opublikowanym) trafia do **kolejki zatwierdzania**
  (`/admin/kolejka`) i staje się publicznie widoczna dopiero, gdy administrator ją zaakceptuje.
  Administrator może też odrzucić przepis z podaniem powodu - redaktor zobaczy go
  na swoim koncie (`/redakcja`) i może poprawić przepis, co wysyła go ponownie do zatwierdzenia.

Konta redaktorów zakłada administrator - nie ma samodzielnej rejestracji. Można to zrobić
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
  Ten format jest przenośny i niezależny od silnika bazy danych - działa niezależnie od tego,
  czy używasz SQLite czy np. PostgreSQL przez `DATABASE_URL`.
- **Importować** wcześniej pobrane archiwum w jednym z trzech trybów:
  - *Uzupełnij i zaktualizuj* - dopasowuje przepisy po tytule/slugu; istniejące nadpisuje danymi z kopii
  - *Dodaj tylko nowe* - pomija przepisy, które już są w bazie
  - *Zastąp wszystko* - usuwa wszystkie obecne przepisy i tagi, potem importuje od zera (nieodwracalne)

### Zalecana praktyka

Regularnie pobieraj kopię zapasową i trzymaj ją **poza serwerem**, na prywatnym komputerze.
Dysk w chmurze byłby dodatkowym odbiorcą danych, więc wymagałby zmiany polityki prywatności.
Z poziomu przeglądarki służy do tego przycisk na `/admin/kopia-zapasowa`; do automatyzacji
(np. przez `cron`) użyj polecenia `flask export-backup` - patrz sekcja „Wdrożenie produkcyjne”.

### Duże kopie zapasowe (limit rozmiaru)

Import kopii zapasowej ogranicza kilka ustawień serwera. Zdjęcia w archiwum prawie się nie
kompresują, więc plik `.zip` ma mniej więcej tyle, ile zajmuje `static/uploads/`. Rozmiar
sprawdzisz poleceniem `du -sh static/uploads` lub po prostu po pobranym pliku kopii.

Domyślnie kopia może mieć do **100 MB**. Jeśli urośnie, zanim wgrasz ją przy odtwarzaniu,
podnieś **razem**:

| Gdzie | Ustawienie | Domyślnie |
|---|---|---|
| `.env` | `MAX_UPLOAD_MB` | `100` |
| nginx, `location = /admin/kopia-zapasowa/import` | `client_max_body_size` (nieco więcej niż `MAX_UPLOAD_MB`) | `110m` |
| `.env` | `BACKUP_MAX_UNCOMPRESSED_MB` (rozmiar po rozpakowaniu) | `300` |
| gunicorn (`--timeout` w usłudze systemd lub `Dockerfile`) oraz nginx (`proxy_read_timeout`) | czas na przetworzenie zdjęć | `120` s |

Po zmianie uruchom ponownie aplikację i przeładuj nginx (`sudo nginx -t && sudo systemctl reload nginx`).
Porównuj rozmiar pobieranej kopii z limitem **zawczasu** - przywracanie po awarii to zły moment
na odkrycie, że plik się nie mieści. Jeśli nginx odrzuci plik, zobaczysz jego stronę `413`;
jeśli aplikacja - komunikat z limitem `MAX_UPLOAD_MB`.

### Usuwanie zdjęć z dysku

Plik zdjęcia znika ze `static/uploads/`, gdy nic już do niego nie odsyła: po zastąpieniu lub
usunięciu zdjęcia, usunięciu przepisu lub wpisu, wycięciu zdjęcia z treści wpisu i po imporcie
kopii. Plik używany jeszcze gdzie indziej zostaje.

Gdy redaktor zastąpi lub usunie zdjęcie w opublikowanym przepisie albo wpisie, poprzedni plik
zostaje do decyzji administratora. Zatwierdzenie zmian go usuwa, a odrzucenie przywraca to
zdjęcie. Treść wraca do redaktora bez zmian, więc nowe zdjęcie trzeba wtedy wgrać ponownie.

Zdjęcia wgrane do wpisu, który nie został ostatecznie zapisany, oraz pliki sprzed tej funkcji
usuwa polecenie (najpierw tylko wypisuje, co by usunęło):

```bash
flask cleanup-images           # lista plików
flask cleanup-images --apply   # usunięcie; pomija pliki młodsze niż 24 h (--min-age-hours)
```

W opcji A: `docker compose exec app flask cleanup-images`. Uruchamiaj je z tym samym `.env` co
aplikację. Przy pustej bazie polecenie odmawia działania, ale z bazą inną niż produkcyjna
uznałoby pliki produkcyjne za nieużywane.

**Usunięcie z serwera nie sięga do pamięci podręcznej:** kto widział zdjęcie, może mieć jego kopię
w przeglądarce (cache i aplikacja offline).

## Migracje bazy danych

Schemat bazy tworzą i aktualizują migracje Alembic (Flask-Migrate) - **nie** `db.create_all()`.
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

Zawsze **przejrzyj** wygenerowany plik przed uruchomieniem - Alembic dobrze radzi sobie
z nowymi kolumnami, ale np. zmiany wymagające wypełnienia danych albo przenoszenia wartości
między kolumnami trzeba dopisać ręcznie.

## Bezpieczeństwo

Aplikacja zawiera kilka wbudowanych zabezpieczeń:

- **SQL injection** - wszystkie zapytania do bazy idą przez ORM SQLAlchemy
  (`Recipe.query.filter(...)`, `.filter_by(...)`, `.ilike(...)` itd.), które zawsze wiąże
  wartości jako parametry, nigdy nie buduje zapytań przez sklejanie surowych stringów SQL.
  W kodzie nie ma ani jednego wywołania `db.session.execute(text(f"..."))` z wartością
  użytkownika wklejoną bezpośrednio w zapytanie.
- **XSS (Cross-Site Scripting)** - Jinja2 domyślnie escapuje wszystko, co wypisujesz przez
  `{{ ... }}` (tytuły, opisy, składniki, tagi, komentarze administratora itd.); w żadnym
  szablonie nie użyto filtra `|safe` ani `{% autoescape false %}`, które mogłyby to wyłączyć.
  Dodatkowo `Content-Security-Policy` na każdej odpowiedzi dopuszcza skrypty wyłącznie
  z własnej domeny (`script-src 'self' 'nonce-...'`, losowy nonce inny dla każdego żądania) -
  bez `'unsafe-inline'`, więc wstrzyknięty przez atak `<script>` albo `onclick="..."`
  nie wykona się nawet, gdyby autoescaping zawiódł. W szablonach nie ma ani jednego
  inline'owego `onclick=`/`onsubmit=` - zamiast tego mały, wspólny plik
  `static/js/app.js` obsługuje potwierdzenia usuwania (`data-confirm="..."`) i
  rozwijanie/zwijanie elementów (`data-toggle-target="..."`) na podstawie atrybutów
  `data-*`, czyli danych, a nie kodu.
- **Bezpieczne przekierowania po logowaniu** - parametr `?next=` jest sprawdzany
  (`is_safe_redirect_target` w `app.py`) i akceptowany tylko, gdy wskazuje na ścieżkę
  wewnątrz tej samej aplikacji; próba przekierowania na obcą domenę (`https://zla-strona.pl`)
  albo adres protokołowo-względny (`//zla-strona.pl`) jest odrzucana - chroni to przed
  wykorzystaniem linku do logowania jako narzędzia phishingu.
- **Unieważnianie sesji** - ciasteczko sesji zawiera losowy znacznik konta
  (`User.session_token`), sprawdzany przy każdym żądaniu. Zmiana lub reset hasła oraz
  wylogowanie zmieniają znacznik, więc kończą sesje na **wszystkich** urządzeniach - także
  skopiowane lub wykradzione ciasteczko przestaje działać. Po zmianie własnego hasła bieżąca
  sesja zostaje (dostaje nowy znacznik). Po wdrożeniu tej zmiany (migracja `d4e5f6a7b8c9`)
  wszyscy zalogowani muszą zalogować się ponownie.
- **Ochrona przed atakiem czasowym (timing attack) i wyliczaniem kont** - logowanie na
  nieistniejące konto wykonuje dokładnie tak samo kosztowne, fikcyjne sprawdzenie hasła
  (`_DUMMY_PASSWORD_HASH`) jak logowanie na istniejące konto ze złym hasłem, więc czas
  odpowiedzi serwera nie zdradza, czy dana nazwa użytkownika w ogóle istnieje w bazie.
  Komunikat błędu jest identyczny we wszystkich przypadkach (zły login, złe hasło,
  zablokowane konto).
- **Wylogowanie tylko przez POST** (z tokenem CSRF) - obca strona nie może wylogować
  użytkownika samym linkiem czy obrazkiem (`<img src="/logout">`); GET na `/logout`
  zwraca teraz 405.
- **Za reverse proxy** (`PROXY_COUNT` w `.env`) - nagłówki `X-Forwarded-For`/`X-Forwarded-Proto`
  są zaufane tylko wtedy, gdy faktycznie skonfigurowano tyle serwerów proxy przed aplikacją.
  Przy `PROXY_COUNT=0` (domyślnie) są całkowicie ignorowane - inaczej ktokolwiek mógłby
  wysłać własny nagłówek `X-Forwarded-For` i podszyć się pod inny adres IP, omijając
  limit prób logowania per IP.
- **Import kopii zapasowej odporny na „zip bombę”** - przed rozpakowaniem sprawdzana jest
  liczba wpisów w archiwum i łączny rozmiar po rozpakowaniu (`BACKUP_MAX_ENTRIES`,
  `BACKUP_MAX_UNCOMPRESSED_MB`); archiwum przekraczające limity jest odrzucane, zanim
  cokolwiek trafi na dysk.
- **Silne hasła wymuszone także w CLI** - `flask create-admin` / `flask create-redaktor`
  i tworzenie redaktora z panelu administratora odrzucają hasła krótsze niż
  `MIN_PASSWORD_LENGTH` (domyślnie 10 znaków) oraz z listy popularnych, słabych haseł
  (`WEAK_PASSWORDS` w `app.py`).
- **Sanityzacja przesyłanych zdjęć** - każdy wgrywany albo wklejany obrazek (a także
  zdjęcia z importowanej kopii zapasowej) jest w całości dekodowany i **ponownie zapisywany
  od zera przez Pillow** (`_sanitize_and_save_image` w `app.py`), zamiast ufać rozszerzeniu
  pliku czy deklarowanemu typowi MIME. Dzięki temu:
  - odrzucane są pliki, które nie są prawdziwymi obrazami (np. przemianowany skrypt,
    plik-polyglot łączący obraz z HTML/JS, uszkodzony/spreparowany plik),
  - usuwane są metadane EXIF (mogą zawierać lokalizację GPS, model urządzenia itp.),
  - usuwane są wszelkie dane doklejone do pliku poza właściwą treścią obrazu,
  - obrazy o podejrzanie dużej liczbie pikseli („bomby dekompresji”) są odrzucane,
    a zwykłe duże zdjęcia proporcjonalnie zmniejszane (`MAX_IMAGE_DIMENSION` w `config.py`),
  - plik zapisywany jest pod nową, losową nazwą (UUID) - nazwa nadana przez użytkownika
    nigdy nie trafia na dysk ani do adresu URL.
  Przed zapychaniem serwera bardzo dużymi plikami chronią limity nginx (`client_max_body_size`,
  w przykładowej konfiguracji 10 MB, a 110 MB tylko dla importu kopii zapasowej) oraz aplikacji
  (`MAX_UPLOAD_MB`, domyślnie 100 MB, musi zmieścić kopię zapasową). Bez nginx obowiązuje tylko ten drugi.
- **Limit prób logowania** - dwie niezależne warstwy ochrony przed atakiem brute-force:
  - limit na poziomie adresu IP przez Flask-Limiter (`LOGIN_RATE_LIMIT` w `config.py`,
    domyślnie 10 prób/minutę i 30/godzinę na jeden adres IP, niezależnie od loginu),
  - blokada konkretnego konta na `LOGIN_LOCKOUT_MINUTES` minut po `LOGIN_MAX_ATTEMPTS`
    nieudanych próbach z rzędu (domyślnie: blokada na 15 minut po 5 próbach) -
    licznik zeruje się po udanym logowaniu.
  Komunikat błędu logowania jest zawsze taki sam niezależnie od tego, czy podana nazwa
  użytkownika w ogóle istnieje w bazie - utrudnia to atakującemu sprawdzanie, które konta
  są zarejestrowane (tzw. ochrona przed username enumeration). Blokada konta to świadomy
  kompromis: ktoś obcy, znając Twój login, może Cię czasowo zablokować, celowo podając
  złe hasło 5 razy - w takiej sytuacji odblokuj konto natychmiast poleceniem
  `flask unlock-user --username nazwa`, bez czekania na upływ `LOGIN_LOCKOUT_MINUTES`.

## Wdrożenie produkcyjne (stawianie serwera)

Poniższa instrukcja zakłada świeży serwer z **Ubuntu 22.04/24.04 lub Debianem 12**, dostęp
przez SSH na użytkownika z `sudo` oraz własną domenę (w przykładach: `twoja-domena.pl`).

### Którą opcję wybrać?

| Opcja | Kiedy | Co działa na serwerze |
|-------|-------|------------------------|
| **A. Docker** | najprościej, łatwe aktualizacje | kontener z gunicornem + nginx na hoście (HTTPS) |
| **B. gunicorn + systemd** | klasyczny VPS bez Dockera | venv + usługa systemd + nginx (HTTPS) |
| **C. Dwa serwery + WireGuard** | publiczny serwer brzegowy (VPS1) i ukryty backend (VPS2) | VPS1: nginx + HTTPS, VPS2: aplikacja (A lub B) dostępna tylko przez tunel |
| **D. Cloudflare Tunnel** | serwer bez publicznego IP albo bez otwartych portów 80/443 (także domowy), domena w Cloudflare | aplikacja (A lub B) + `cloudflared`, bez nginx i certyfikatu |

W opcjach A-C ruch z internetu trafia **najpierw do nginx** (HTTPS), który przekazuje
go do gunicorna na porcie `8000`. W opcji D tę rolę przejmuje Cloudflare. Gunicorn nigdy
nie powinien być dostępny bezpośrednio z internetu.

```
przeglądarka ──HTTPS:443──▶ nginx ──HTTP:8000──▶ gunicorn (wsgi:app) ──▶ SQLite + static/uploads
```

### Krok 1: Przygotowanie serwera (wszystkie opcje)

```bash
# Aktualizacja systemu i potrzebne pakiety
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx certbot ufw
sudo apt install -y python3 python3-venv     # tylko opcja B (w opcji A Python jest w obrazie)

# Zapora: SSH + HTTP/HTTPS (port 8000 NIE jest otwierany na zewnątrz)
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

W panelu swojego rejestratora domen ustaw rekord **A** (i ewentualnie **AAAA**) domeny
na publiczny adres IP serwera. Sprawdź, zanim przejdziesz dalej (certyfikat SSL bez tego
się nie wystawi):

```bash
dig +short twoja-domena.pl     # powinno zwrócić IP serwera
```

### Krok 2: Kod aplikacji i plik `.env` (wszystkie opcje)

```bash
sudo git clone <adres-repozytorium> /opt/recipe-app
sudo chown -R $USER:$USER /opt/recipe-app
cd /opt/recipe-app

# Wygeneruj klucz sesji (min. 32 znaki - bez niego aplikacja odmówi startu)
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Utwórz `/opt/recipe-app/.env` (`cp .env.example .env`, potem `nano .env`) - minimalna konfiguracja
produkcyjna:

```ini
APP_ENV=production
SECRET_KEY=<wklej-wygenerowany-klucz>
# Jeden nginx przed aplikacją = 1. Źle ustawione psuje limit logowań per IP i wykrywanie HTTPS.
PROXY_COUNT=1
# Domena(-y) serwisu, po przecinku. Inny nagłówek Host = błąd 400 (ochrona przed podrobionym Host).
TRUSTED_HOSTS=twoja-domena.pl
# Tylko opcja B: baza w osobnym katalogu (patrz krok B3). W opcji A ustawia to docker-compose.
DATABASE_URL=sqlite:////opt/recipe-app/data/recipes.db
# Tylko opcja B: liczniki limitów w Redisie (patrz krok B2a). W opcji A ustawia to docker-compose.
RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
# Opcjonalnie: domyślny login dla `flask create-admin`
ADMIN_USERNAME=admin
```

```bash
chmod 600 .env     # w opcji B uprawnienia poprawimy w kroku B3
```

Pełna lista zmiennych - patrz sekcja „Zmienne środowiskowe” wyżej.

### Krok 3: Certyfikat SSL (Let's Encrypt)

Wystawiamy certyfikat **przed** skonfigurowaniem nginx, bo przykładowy `deploy/nginx.conf.example`
odwołuje się do plików certyfikatu - bez nich `nginx -t` zgłosi błąd. Certbot w trybie
`standalone` potrzebuje na chwilę wolnego portu 80, stąd zatrzymanie nginx; hooki sprawiają,
że automatyczne odnawianie (timer `certbot.timer`) zrobi to samo bez Twojego udziału.

```bash
sudo certbot certonly --standalone -d twoja-domena.pl \
  --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx"

sudo certbot renew --dry-run     # test odnawiania
```

W opcji C wykonaj ten krok na **VPS1**.

---

### Opcja A: Docker / docker-compose

**A1. Instalacja Dockera** (oficjalny skrypt; alternatywnie pakiety z docs.docker.com):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER     # wyloguj się i zaloguj ponownie, żeby zadziałało
```

**A2. Konfiguracja compose:**

```bash
cd /opt/recipe-app
cp docker-compose.yml.example docker-compose.yml
nano docker-compose.yml
```

Przykład mapuje port jako `"127.0.0.1:8000:8000"` - **nie zmieniaj tego na `"8000:8000"`**.
Docker sam dopisuje reguły iptables i **omija `ufw`**, więc wtedy gunicorn byłby dostępny
z internetu po zwykłym HTTP, z pominięciem nginx. Usuń też z `.env` linię `DATABASE_URL` -
w kontenerze ustawia ją `docker-compose.yml` (`sqlite:////data/recipes.db`).

**A3. Budowa, migracje, konto admina, start:**

```bash
docker compose build
docker compose run --rm app flask db upgrade            # schemat bazy (zawsze przed startem)
docker compose run --rm app flask create-admin --username admin   # zapyta o hasło
docker compose up -d

docker compose ps                                       # STATUS powinien dojść do "healthy"
curl http://127.0.0.1:8000/healthz                      # {"status":"ok"}
```

Baza SQLite i przesłane zdjęcia żyją w nazwanych wolumenach Dockera (`db-data`,
`uploads-data`), więc przetrwają przebudowę obrazu. Kontener działa jako użytkownik bez
uprawnień roota i ma `HEALTHCHECK` na `/healthz`. Migracje **nie** uruchamiają się same
przy starcie kontenera.

**A4. nginx** - tak jak w kroku B5 niżej, z jedną zmianą: **usuń** z konfiguracji blok
`location /static/ { ... }`. Pliki statyczne i zdjęcia są wewnątrz kontenera/wolumenu,
a nie w `/opt/recipe-app/static/` na hoście - gunicorn serwuje je sam.

**Aktualizacja do nowej wersji:**

```bash
cd /opt/recipe-app
git pull
docker compose build
docker compose run --rm app flask db upgrade
docker compose up -d
```

Logi: `docker compose logs -f app`.

---

### Opcja B: gunicorn + nginx + systemd (serwer VPS)

Usługa działa jako użytkownik `www-data` (tak jak w `deploy/recipe-app.service.example`),
więc katalogi, do których aplikacja zapisuje, muszą należeć do niego.

**B1. Środowisko Pythona:**

```bash
cd /opt/recipe-app
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

**B2. Katalogi z danymi:**

```bash
mkdir -p data instance static/uploads
sudo chown -R www-data:www-data data instance static/uploads
```

Baza leży w osobnym katalogu `data/` (patrz `DATABASE_URL` w `.env`), bo aplikacja włącza
w SQLite tryb WAL - obok `recipes.db` muszą móc powstać pliki `recipes.db-wal` i
`recipes.db-shm`. Jednostka systemd ma `ProtectSystem=strict`, czyli zapisywać można tylko
w katalogach z `ReadWritePaths`; samo `recipes.db` w katalogu projektu nie wystarczy.

**B2a. Redis** - gunicorn działa w 4 workerach, więc limity prób logowania muszą być liczone
wspólnie (w opcji A kontener Redisa uruchamia `docker-compose`):

```bash
sudo apt install -y redis-server
sudo systemctl enable --now redis-server
redis-cli ping      # powinno odpowiedzieć PONG
```

Domyślnie Redis w Debianie/Ubuntu słucha tylko na `127.0.0.1` - nie otwieraj jego portu na zewnątrz.

**B3. Uprawnienia `.env`** - aplikacja (jako `www-data`) też czyta ten plik:

```bash
sudo chown $USER:www-data .env
chmod 640 .env
```

**B4. Migracje i konto administratora** (jako `www-data`, żeby baza od razu miała
właściwego właściciela):

```bash
sudo -u www-data venv/bin/flask --app app db upgrade
sudo -u www-data venv/bin/flask --app app create-admin --username admin   # zapyta o hasło
```

**B5. Usługa systemd:**

```bash
sudo cp deploy/recipe-app.service.example /etc/systemd/system/recipe-app.service
sudo nano /etc/systemd/system/recipe-app.service
```

W pliku zamień linię `ReadWritePaths=` na:

```ini
ReadWritePaths=/opt/recipe-app/data /opt/recipe-app/static/uploads /opt/recipe-app/instance
```

(wszystkie trzy katalogi muszą istnieć - inaczej systemd nie uruchomi usługi). Jeśli
zmieniłeś ścieżkę instalacji albo użytkownika, popraw też `WorkingDirectory`,
`EnvironmentFile`, `ExecStart` i `User`/`Group`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now recipe-app
sudo systemctl status recipe-app
curl http://127.0.0.1:8000/healthz      # {"status":"ok"}
```

**B6. nginx** (reverse proxy + HTTPS):

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/recipe-app
sudo sed -i 's/twoja-domena.pl/TWOJA.DOMENA/g' /etc/nginx/sites-available/recipe-app
sudo ln -s /etc/nginx/sites-available/recipe-app /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default        # domyślna strona „Welcome to nginx”
sudo nginx -t && sudo systemctl reload nginx
```

Zdjęcia ogranicza ogólny `client_max_body_size` (10 MB). Dla importu kopii zapasowej nginx ma
osobny limit, który musi być nieco większy niż `MAX_UPLOAD_MB` z `.env` - patrz
„Duże kopie zapasowe (limit rozmiaru)”.

**Aktualizacja do nowej wersji:**

```bash
cd /opt/recipe-app
git pull
venv/bin/pip install -r requirements.txt
sudo -u www-data venv/bin/flask --app app db upgrade
sudo systemctl restart recipe-app
```

Logi: `journalctl -u recipe-app -f` (aplikacja/gunicorn), `/var/log/nginx/error.log` (nginx).

`wsgi.py` to punkt wejścia dla gunicorna (`gunicorn wsgi:app`) - patrz komentarz w pliku.

---

### Opcja C: dwa serwery połączone WireGuardem

Układ: **VPS1** (publiczny, „brzegowy”) ma nginx i certyfikat SSL; **VPS2** (backend)
uruchamia aplikację, która nasłuchuje tylko w tunelu (`10.10.10.2:8000`) i nie jest widoczna
z internetu. To tunel punkt-do-punktu, nie pełny VPN - szczegóły w komentarzach plików
`deploy/wireguard/*.conf.example`.

**Oba serwery muszą być u dostawcy wskazanego w polityce prywatności** (sekcja 4
`templates/privacy.html`: Korbank SA, serwery w Polsce). VPS1 też przetwarza dane osobowe
(logi nginx z adresami IP), więc jeśli którykolwiek serwer stoi u innego dostawcy, dopisz go
w polityce jako odbiorcę danych, a poza EOG opisz też przekazywanie danych.

**C1. WireGuard na obu serwerach:**

```bash
sudo apt install -y wireguard
# klucze generuj osobno na każdym serwerze (polecenia w komentarzach plików .example)
sudo cp deploy/wireguard/vps1-wg0.conf.example /etc/wireguard/wg0.conf   # na VPS1
sudo cp deploy/wireguard/vps2-wg0.conf.example /etc/wireguard/wg0.conf   # na VPS2
sudo nano /etc/wireguard/wg0.conf      # wpisz klucze i publiczne adresy IP
sudo chmod 600 /etc/wireguard/wg0.conf
sudo systemctl enable --now wg-quick@wg0
```

Na VPS1 otwórz port tunelu: `sudo ufw allow 51820/udp`. Sprawdź połączenie:
`ping 10.10.10.2` z VPS1 i `sudo wg show` (powinien być widoczny „latest handshake”).

**C2. Aplikacja na VPS2** - kroki 1–2 oraz opcja A albo B, z tymi różnicami:

- nginx i certyfikat **nie** są potrzebne na VPS2,
- opcja B: w `ExecStart` jednostki systemd zmień `--bind 127.0.0.1:8000` na
  `--bind 10.10.10.2:8000`, a w sekcji `[Unit]` dopisz `After=wg-quick@wg0.service` i
  `Requires=wg-quick@wg0.service` (adres tunelu musi istnieć przed startem gunicorna),
- opcja A: mapowanie portu w `docker-compose.yml` ustaw na `"10.10.10.2:8000:8000"`,
- zapora na VPS2 - port aplikacji tylko z tunelu:
  `sudo ufw allow in on wg0 to any port 8000 proto tcp`,
- `PROXY_COUNT=1` (jedynym proxy jest nginx na VPS1).

**C3. nginx na VPS1** - krok 3 (certyfikat) i krok B6, ale w konfiguracji nginx:

- `proxy_pass http://10.10.10.2:8000;` zamiast `http://127.0.0.1:8000`,
- **usuń** blok `location /static/ { ... }` - pliki statyczne są na VPS2.

Test z VPS1: `curl -H "Host: twoja-domena.pl" http://10.10.10.2:8000/healthz`
(nagłówek Host jest potrzebny, bo przy ustawionym `TRUSTED_HOSTS` aplikacja odrzuca
żądania zaadresowane samym IP tunelu).

---

### Opcja D: Cloudflare Tunnel

Układ: `cloudflared` na serwerze zestawia **wychodzące** połączenie do Cloudflare, a HTTPS
kończy się na brzegu Cloudflare. Serwer nie potrzebuje publicznego IP ani otwartych portów
80/443. Domena musi być dodana do konta Cloudflare (serwery nazw wskazują na Cloudflare).

**Polityka prywatności nie uwzględnia Cloudflare.** Przed wyborem tej opcji zaktualizuj
`templates/privacy.html`: dopisz Cloudflare jako odbiorcę danych, opisz przekazywanie danych poza
EOG, popraw zdanie o wczytywaniu wszystkiego z własnego serwera i sprawdź ciasteczka Cloudflare.

```
przeglądarka ──HTTPS──▶ Cloudflare ◀──tunel── cloudflared ──HTTP:8000──▶ gunicorn (wsgi:app)
```

Instrukcja zakłada tunel **bezpośrednio do gunicorna**, bez nginx. Pliki statyczne i zdjęcia
serwuje wtedy sam gunicorn.

**D1. Serwer i aplikacja** - wykonaj kroki 1 i 2 oraz opcję A albo B, z tymi zmianami:

- w kroku 1 pomiń `nginx` i `certbot`, regułę `ufw allow 'Nginx Full'` oraz rekord A/AAAA,
- pomiń krok 3 (certyfikat) i całą konfigurację nginx (kroki A4 oraz B6),
- zostaw gunicorna na `127.0.0.1:8000` (w Dockerze `"127.0.0.1:8000:8000"`),
- w `.env` ustaw `PROXY_COUNT=1` (jedynym proxy z nagłówkami jest Cloudflare) i
  `TRUSTED_HOSTS=twoja-domena.pl`.

Sprawdź lokalnie: `curl http://127.0.0.1:8000/healthz` powinno zwrócić `{"status":"ok"}`.

**D2. Instalacja `cloudflared`:**

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared
```

**D3. Tunel i DNS** (jako zwykły użytkownik, bez `sudo`):

```bash
cloudflared tunnel login                 # otwiera link do logowania i wyboru domeny
cloudflared tunnel create recipe-app     # wypisze UUID tunelu i ścieżkę do pliku .json
cloudflared tunnel route dns recipe-app twoja-domena.pl
```

**D4. Konfiguracja** - utwórz `~/.cloudflared/config.yml`:

```yaml
tunnel: <UUID-tunelu>
credentials-file: /home/<uzytkownik>/.cloudflared/<UUID-tunelu>.json

ingress:
  - hostname: twoja-domena.pl
    service: http://127.0.0.1:8000
  # Wymagana reguła końcowa: inne domeny dostają 404.
  - service: http_status:404
```

Nie ustawiaj `httpHostHeader`: aplikacja ma dostać oryginalny nagłówek `Host`, bo sprawdza go
`TRUSTED_HOSTS` i buduje z niego adresy w `sitemap.xml`.

```bash
cloudflared tunnel ingress validate
cloudflared tunnel run recipe-app        # test na pierwszym planie, zakończ przez Ctrl+C
```

**D5. Uruchomienie jako usługa:**

```bash
sudo cloudflared --config /home/<uzytkownik>/.cloudflared/config.yml service install
sudo systemctl start cloudflared
systemctl status cloudflared
```

Po każdej zmianie `config.yml`: `sudo systemctl restart cloudflared`.

**D6. Ustawienia w panelu Cloudflare i weryfikacja:**

- Włącz **Always Use HTTPS** (SSL/TLS → Edge Certificates). Bez tego wejście przez `http://`
  dotrze do aplikacji, a ciasteczko sesji działa tylko przez HTTPS.
- Sprawdź, czy limity działają per użytkownik: zaloguj się przez `https://twoja-domena.pl`
  i poszukaj wpisu `Zalogowano` w logu (`journalctl -u recipe-app` albo
  `docker compose logs app`). Pole `ip=` musi pokazywać **Twój publiczny adres**. Jeśli widać
  `127.0.0.1` albo adres Cloudflare, wszyscy czytelnicy dzielą jeden limit: popraw `PROXY_COUNT`.

Co warto wiedzieć w tej opcji:

- **Limit wysyłania:** na planie Free Cloudflare odrzuca żądania ponad **100 MB** błędem `413`,
  zanim dotrą do serwera. To dotyczy importu kopii zapasowej i nie zmieni tego `MAX_UPLOAD_MB`,
  więc rozmiar kopii sprawdzaj zawczasu.
- **Długie żądania:** import z dużą liczbą zdjęć może skończyć się w przeglądarce błędem `524`
  (przekroczony czas Cloudflare). Serwer może wtedy nadal kończyć pracę, więc przed ponowną
  próbą sprawdź log i stan bazy.
- **Cache:** `style.css` i pliki JS mają stałe adresy, a Cloudflare może je przechowywać.
  Po wdrożeniu nowej wersji wyczyść cache w panelu (Caching → Purge Cache).
- **Nie dokładaj nginx między tunel a gunicorna** bez zmiany tej konfiguracji: nginx nadpisuje
  `X-Forwarded-Proto` i dopisuje się do `X-Forwarded-For`, więc samo `PROXY_COUNT` przestanie
  się zgadzać.

---

### Krok końcowy: weryfikacja (wszystkie opcje)

```bash
curl -I http://twoja-domena.pl            # 301 → https://
curl https://twoja-domena.pl/healthz      # {"status":"ok"}
```

Następnie otwórz `https://twoja-domena.pl/login`, zaloguj się na konto administratora i
dodaj testowy przepis ze zdjęciem (sprawdza zapis do bazy i do `static/uploads`).

### Logi: maksymalnie 30 dni

Polityka prywatności obiecuje, że logi z adresami IP są przechowywane **30 dni**. Aplikacja
nie zapisuje własnych plików z logami, więc usuwaniem zajmuje się system. Wystarczy raz zainstalować
gotowe pliki z `deploy/`, a dalej działa to automatycznie. Zrób to na każdym serwerze z logami:

```bash
cd /opt/recipe-app

# journald: logi aplikacji (usługa systemd i kontener)
sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp deploy/journald-retention.conf.example /etc/systemd/journald.conf.d/retention.conf
sudo systemctl restart systemd-journald

# nginx (opcje A-C): zastępuje domyślną regułę logrotate
sudo cp deploy/logrotate-nginx.conf.example /etc/logrotate.d/nginx
sudo logrotate -d /etc/logrotate.d/nginx     # test bez zmian na dysku
```

- **Docker (opcja A):** domyślny sterownik logów nie usuwa wpisów po czasie, dlatego
  `docker-compose.yml.example` kieruje logi do journald, gdzie obowiązuje limit 30 dni.
  Po zmianie uruchom kontener ponownie: `docker compose up -d --force-recreate app`.
- **Zmiana okresu:** popraw oba pliki i `templates/privacy.html`.

### Kopie zapasowe przez cron

Kopie powstają na serwerze co noc i zostają tam **7 dni**, a Twój komputer pobiera je i trzyma
**90 dni**. Te okresy podaje polityka prywatności, więc zmieniając je, zaktualizuj też
`templates/privacy.html`.

Katalog `/backups` musi istnieć i należeć do użytkownika, który tworzy kopie. Poniżej
`<uzytkownik>` to konto SSH, przez które komputer pobiera pliki.

Opcja B (crontab roota: `sudo crontab -e`; `/backups` należy do `www-data`):

```bash
# backup codziennie o 3:00; plik przekazany kontu SSH, bo eksport zapisuje go z uprawnieniami 600
0 3 * * * F=/backups/przepisy-$(date +\%F).zip; cd /opt/recipe-app && sudo -u www-data venv/bin/flask --app app export-backup -o "$F" && chown <uzytkownik> "$F"
# usuwanie kopii na serwerze po 7 dniach
30 3 * * * find /backups -name 'przepisy-*.zip' -mtime +6 -delete
```

Opcja A (crontab konta `<uzytkownik>`, które musi należeć do grupy `docker`; plik skopiowany
z kontenera należy do właściciela crontaba, więc to musi być to samo konto, przez które komputer
pobiera kopie):

```bash
# backup codziennie o 3:00; kopia tymczasowa w kontenerze jest usuwana zawsze, także po błędzie
0 3 * * * cd /opt/recipe-app && docker compose exec -T app flask export-backup -o /tmp/kopia.zip && docker compose cp app:/tmp/kopia.zip /backups/przepisy-$(date +\%F).zip; docker compose exec -T app rm -f /tmp/kopia.zip
30 3 * * * find /backups -name 'przepisy-*.zip' -mtime +6 -delete
```

`flask export-backup` działa bez przeglądarki/sesji i zapisuje plik z uprawnieniami `600`
(czytelny tylko dla właściciela) - patrz sekcja „Kopia zapasowa przepisów” wyżej.

**Pobieranie na prywatny komputer (Linux).** Komputer potrzebuje klucza SSH bez hasła do konta
`<uzytkownik>` i folderu na kopie (`mkdir -p ~/kopie-szczypta`). W crontabie komputera (`crontab -e`):

```bash
# co godzinę pobiera nowe kopie (cron nie nadrabia pominiętych uruchomień, więc pojedyncza
# godzina łatwo trafiłaby na wyłączony komputer); rsync pomija pliki już pobrane
0 * * * * rsync -rt --include='przepisy-*.zip' --exclude='*' <uzytkownik>@<adres-serwera>:/backups/ ~/kopie-szczypta/
# usuwanie lokalnych kopii starszych niż 90 dni - niezależnie od tego, czy pobieranie działa
30 * * * * find ~/kopie-szczypta -name 'przepisy-*.zip' -mtime +89 -delete
```

- Wyłączony komputer niczego nie traci, dopóki włączysz go w ciągu 7 dni (na co najmniej
  godzinę): `rsync` pobierze wszystkie zaległe kopie. Usunięcie pliku z serwera nie usuwa go
  z komputera.
- Lokalne kopie są usuwane po 90 dniach także wtedy, gdy pobieranie przestanie działać
  (np. po zmianie adresu serwera), więc sprawdzaj czasem, czy w folderze pojawiają się nowe pliki.
- Kopie zawierają dane osobowe (komentarze, skróty IP, oceny, dane o autorach), więc włącz
  szyfrowanie dysku. Logi do kopii nie trafiają.
- Dane usunięte z serwisu, np. komentarz na prośbę autora, zostają w starszych kopiach najwyżej
  90 dni. Po przywróceniu kopii usuń je ponownie.

### Najczęstsze problemy

| Objaw | Przyczyna i rozwiązanie |
|-------|--------------------------|
| Usługa/kontener nie startuje, w logu „Odmowa startu - niebezpieczna konfiguracja” | Brak lub za krótki `SECRET_KEY` w `.env` (min. 32 znaki). |
| `502 Bad Gateway` z nginx | Gunicorn nie działa albo słucha na innym adresie - `systemctl status recipe-app` / `docker compose ps`, sprawdź `curl` na `/healthz` lokalnie. |
| Logowanie „nie działa” (wraca na stronę logowania), błąd CSRF | Strona otwarta po zwykłym `http://` - ciasteczko sesji jest tylko dla HTTPS. Wejdź przez `https://` i sprawdź `PROXY_COUNT=1`. |
| `attempt to write a readonly database` / `unable to open database file` | Katalog z bazą nie należy do `www-data` albo nie ma go w `ReadWritePaths` (krok B2 i B5). |
| Błąd przy zapisie zdjęcia | `static/uploads` nie należy do `www-data` / brak w `ReadWritePaths`. |
| `413` przy imporcie kopii w opcji D, bez śladu w logu aplikacji | Limit Cloudflare (plan Free: 100 MB) - patrz „Opcja D: Cloudflare Tunnel”. |
| `502`/`1033` z Cloudflare w opcji D | Tunel nie działa albo gunicorn nie słucha na `127.0.0.1:8000` - `systemctl status cloudflared`, sprawdź `curl` na `/healthz` lokalnie. |
| `413 Request Entity Too Large` | Przy zdjęciu: plik przekracza ogólny `client_max_body_size` (10 MB). Przy imporcie kopii: patrz „Duże kopie zapasowe (limit rozmiaru)”. |
| Konto admina zablokowane po błędnych hasłach | `flask unlock-user --username admin` (w opcji A przez `docker compose exec app ...`). |

### Lista kontrolna przed pierwszym uruchomieniem na produkcji

- [ ] `SECRET_KEY` wygenerowany (`python3 -c "import secrets; print(secrets.token_hex(32))"`)
      i ustawiony w `.env` - bez tego aplikacja **odmówi startu** (patrz `validate_production_config`).
- [ ] `APP_ENV=production` (domyślne - po prostu nie ustawiaj `development` na serwerze).
- [ ] Aplikacja dostępna wyłącznie przez HTTPS (nginx + certyfikat albo w opcji D Cloudflare
      z włączonym Always Use HTTPS); `SESSION_COOKIE_SECURE` zostaje na `true` (domyślne w production).
- [ ] `TRUSTED_HOSTS` ustawione na domenę serwisu, a nginx ma bloki `default_server`
      odrzucające nieznane domeny (patrz `deploy/nginx.conf.example`). W opcji D tę rolę pełni
      końcowa reguła `http_status:404` w `config.yml`.
- [ ] Port `8000` niedostępny z internetu (bind na `127.0.0.1` / adres tunelu; w Dockerze
      mapowanie `127.0.0.1:8000:8000`, bo Docker omija `ufw`).
- [ ] `PROXY_COUNT` ustawiony na dokładną liczbę serwerów proxy przed aplikacją (zwykle `1`
      dla pojedynczego nginx albo samego Cloudflare Tunnel) - źle ustawiony psuje limit logowań per IP i wykrywanie HTTPS.
- [ ] Hasło administratora nadane przy `flask create-admin` jest unikalne i silne
      (min. 10 znaków, nie z listy popularnych - wymuszane automatycznie).
- [ ] Migracje zastosowane (`flask db upgrade`) **przed** pierwszym uruchomieniem gunicorna
      i po każdej aktualizacji kodu.
- [ ] Kopie zapasowe skonfigurowane (cron + `flask export-backup`): 7 dni na serwerze, 90 dni na
      prywatnym komputerze z szyfrowanym dyskiem (patrz „Kopie zapasowe przez cron”).
- [ ] Przy więcej niż jednym workerze gunicorna (domyślnie jest ich 4): `RATELIMIT_STORAGE_URI`
      wskazuje na Redis, a nie zostaje na `memory://` (inaczej każdy worker liczy próby
      logowania osobno). W opcji A ustawia to `docker-compose.yml`, w opcji B patrz krok B2a.
      Przy `memory://` na produkcji aplikacja zapisuje ostrzeżenie w logu. Gdy Redis jest
      niedostępny, logowanie działa dalej, a limity są liczone osobno w każdym workerze.
- [ ] Logi usuwane po 30 dniach, tak jak obiecuje polityka prywatności (patrz „Logi: maksymalnie 30 dni”).
- [ ] `.env` nie trafia do systemu kontroli wersji (już w `.gitignore`) i nie jest czytelny dla
      innych użytkowników (`600`, w opcji B `640` z grupą `www-data`).
