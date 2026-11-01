from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# Dozwolone jednostki miary składników.
INGREDIENT_UNITS = ["g", "ml", "szt"]

# Dozwolone role użytkowników.
# admin -> pełne prawa (dodaje/edytuje/usuwa/zatwierdza wszystko)
# redaktor -> może tworzyć i edytować WŁASNE przepisy, ale trafiają one do kolejki
#             i stają się publiczne dopiero po zatwierdzeniu przez administratora
ROLES = {"admin": "Administrator", "redaktor": "Redaktor"}

# Statusy przepisu w cyklu redakcyjnym.
RECIPE_STATUSES = {
    "published": "Opublikowany",
    "pending": "Oczekuje na zatwierdzenie",
    "rejected": "Odrzucony",
}

# Dozwolone kształty formy do pieczenia.
# okragla -> jeden wymiar (średnica), prostokatna -> dwa wymiary (bok x bok)
PAN_SHAPES = {"okragla": "okrągła", "prostokatna": "prostokątna"}

# Tabela pośrednicząca dla relacji wiele-do-wielu Recipe <-> Tag
recipe_tags = db.Table(
    "recipe_tags",
    db.Column("recipe_id", db.Integer, db.ForeignKey("recipes.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    """
    Reprezentuje użytkownika systemu.
    - admin: pełne prawa, w tym zatwierdzanie/odrzucanie przepisów redaktorów
    - redaktor: może tworzyć/edytować WŁASNE przepisy, ale wymagają one
      zatwierdzenia przez administratora, zanim staną się publicznie widoczne
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="admin")

    # Ochrona przed atakami brute-force na logowanie: licznik nieudanych prób
    # i czas, do którego konto jest tymczasowo zablokowane.
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def register_failed_login(self, max_attempts: int = 5, lockout_minutes: int = 15) -> None:
        """Zwiększa licznik nieudanych prób logowania i blokuje konto po przekroczeniu limitu."""
        from datetime import timedelta

        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)
            self.failed_login_attempts = 0

    def register_successful_login(self) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_redaktor(self):
        return self.role == "redaktor"

    @property
    def role_display(self):
        return ROLES.get(self.role, self.role)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Recipe(db.Model):
    """Pojedynczy przepis kulinarny."""

    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    description = db.Column(db.String(300))
    # Każda linia w formacie "ilość|jednostka|nazwa składnika", np. "200|g|mąki pszennej"
    ingredients = db.Column(db.Text, nullable=False)
    # Jeden krok na linię
    instructions = db.Column(db.Text, nullable=False)
    servings = db.Column(db.Integer)
    image_url = db.Column(db.String(500))

    # Forma do pieczenia: kształt ("okragla" / "prostokatna")
    # okragla -> pan_size_cm to średnica
    # prostokatna -> pan_width_cm x pan_length_cm to boki formy
    pan_shape = db.Column(db.String(20))
    pan_size_cm = db.Column(db.Integer)
    pan_width_cm = db.Column(db.Integer)
    pan_length_cm = db.Column(db.Integer)

    # Cykl redakcyjny: przepisy dodane przez admina są od razu "published";
    # przepisy dodane/edytowane przez redaktora wracają do "pending", dopóki
    # administrator ich nie zatwierdzi (albo nie odrzuci, z uzasadnieniem).
    status = db.Column(db.String(20), nullable=False, default="published")
    rejection_reason = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = db.relationship("User", backref="recipes")
    tags = db.relationship("Tag", secondary=recipe_tags, back_populates="recipes", order_by="Tag.name")

    # Znacznik linii nagłówka sekcji składników w tekście `ingredients`, np.:
    #   ##SECTION##Ciasto
    #   200|g|mąki pszennej
    #   ##SECTION##Krem
    #   500|g|mascarpone
    # Linie przed pierwszym nagłówkiem sekcji trafiają do sekcji "bez nazwy".
    SECTION_MARKER = "##SECTION##"

    @property
    def ingredients_sections(self):
        """
        Zwraca listę sekcji składników: [{"name": "Ciasto"|None, "items": [...]}, ...].
        "name" to None dla składników nienależących do żadnej nazwanej sekcji
        (czyli zwykła, niepodzielona lista — najczęstszy przypadek).
        """
        sections = []
        current = {"name": None, "items": []}
        has_current_content = False

        for raw_line in (self.ingredients or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith(self.SECTION_MARKER):
                if has_current_content:
                    sections.append(current)
                current = {"name": line[len(self.SECTION_MARKER):].strip() or None, "items": []}
                has_current_content = True  # sekcja istnieje, nawet zanim dostanie składniki
                continue

            # Pola nigdy nie zawierają "|" (usuwane przy zapisie), więc liczba
            # części jednoznacznie mówi, czy to stary wpis (bez wartości
            # odżywczych) czy nowy (amount|unit|kcal|białko|tłuszcz|węgl.|nazwa).
            parts = line.split("|")
            if len(parts) >= 7:
                amount, unit, kcal, protein, fat, carbs = (p.strip() for p in parts[:6])
                name = "|".join(parts[6:]).strip()  # na wszelki wypadek, gdyby jednak trafił się "|"
            else:
                amount = parts[0].strip() if len(parts) > 0 else ""
                unit = parts[1].strip() if len(parts) > 1 else ""
                name = parts[2].strip() if len(parts) > 2 else ""
                kcal = protein = fat = carbs = ""
            if not name:
                continue
            current["items"].append(
                {
                    "amount": amount, "unit": unit, "name": name,
                    "kcal": kcal, "protein": protein, "fat": fat, "carbs": carbs,
                }
            )
            has_current_content = True

        if has_current_content:
            sections.append(current)

        # Nie pokazujemy pustych nazwanych sekcji (np. dodanej, a potem nie wypełnionej)
        return [s for s in sections if s["items"] or s["name"] is None]

    @property
    def ingredients_list(self):
        """Płaska lista {amount, unit, name} ze wszystkich sekcji — dla kodu, któremu
        podział na sekcje jest obojętny (np. eksport do starszego formatu kopii zapasowej)."""
        return [item for section in self.ingredients_sections for item in section["items"]]

    @property
    def has_ingredient_sections(self):
        """True, jeśli składniki są podzielone na co najmniej jedną NAZWANĄ sekcję."""
        return any(section["name"] for section in self.ingredients_sections)

    @staticmethod
    def _to_float(value):
        try:
            return float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None

    @property
    def nutrition_totals(self):
        """
        Suma kcal/białka/tłuszczu/węglowodanów ze wszystkich składników, które mają
        podaną choć jedną wartość liczbową. Brakujące/nieliczbowe pola są pomijane
        (nie liczone jako 0) — suma więc zawsze jest przynajmniej tak duża, jak dane
        pozwalają, a `has_data` mówi, czy w ogóle jest co sumować.
        """
        totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
        has_data = False
        for item in self.ingredients_list:
            for key in totals:
                value = self._to_float(item.get(key))
                if value is not None:
                    totals[key] += value
                    has_data = True
        return {"has_data": has_data, **totals}

    @property
    def nutrition_per_serving(self):
        """Wartości odżywcze podzielone przez liczbę porcji (None, jeśli brak danych/porcji)."""
        totals = self.nutrition_totals
        if not totals["has_data"] or not self.servings:
            return None
        return {key: totals[key] / self.servings for key in ("kcal", "protein", "fat", "carbs")}

    @property
    def instructions_list(self):
        return [line.strip() for line in (self.instructions or "").splitlines() if line.strip()]

    @property
    def pan_shape_display(self):
        return PAN_SHAPES.get(self.pan_shape, "")

    @property
    def status_display(self):
        return RECIPE_STATUSES.get(self.status, self.status)

    @property
    def is_published(self):
        return self.status == "published"

    @property
    def pan_dimensions_display(self):
        """Zwraca czytelny opis wymiarów formy, np. 'okrągła, 24 cm' albo 'prostokątna, 20x30 cm'."""
        if not self.pan_shape:
            return ""
        if self.pan_shape == "okragla" and self.pan_size_cm:
            return f"{self.pan_shape_display}, {self.pan_size_cm} cm"
        if self.pan_shape == "prostokatna" and self.pan_width_cm and self.pan_length_cm:
            return f"{self.pan_shape_display}, {self.pan_width_cm}x{self.pan_length_cm} cm"
        return self.pan_shape_display

    def __repr__(self):
        return f"<Recipe {self.title}>"


class Tag(db.Model):
    """Tag/kategoria przypisywana do przepisów, np. 'obiad', 'wegańskie', 'deser'."""

    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)

    recipes = db.relationship("Recipe", secondary=recipe_tags, back_populates="tags")

    def __repr__(self):
        return f"<Tag {self.name}>"
