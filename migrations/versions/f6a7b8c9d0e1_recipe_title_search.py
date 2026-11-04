"""recipe title_search (wyszukiwanie bez rozróżniania wielkości liter i polskich znaków)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-04 18:00:00.000000

SQLite przy LIKE ignoruje wielkość liter tylko dla ASCII, więc 'żurek' nie znajdował
'Żurek'. Kolumna trzyma tytuł w postaci znormalizowanej, a aplikacja szuka po niej.
"""
import unicodedata

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def _fold(text):
    # Kopia models.fold_search_text - migracja nie może zależeć od przyszłych zmian w modelach.
    text = str(text).casefold().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def upgrade():
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title_search', sa.Text(), nullable=False, server_default=''))

    bind = op.get_bind()
    recipes = sa.table('recipes', sa.column('id', sa.Integer), sa.column('title', sa.String),
                       sa.column('title_search', sa.Text))
    for recipe_id, title in bind.execute(sa.select(recipes.c.id, recipes.c.title)).fetchall():
        bind.execute(recipes.update().where(recipes.c.id == recipe_id).values(title_search=_fold(title)))


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        # Jak w d4e5f6a7b8c9: przebudowa tabeli recipes byłaby blokowana przez klucze obce.
        op.execute("ALTER TABLE recipes DROP COLUMN title_search")
    else:
        op.drop_column('recipes', 'title_search')
