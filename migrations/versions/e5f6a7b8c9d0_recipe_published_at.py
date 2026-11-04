"""recipe published_at (redaktor nie może usunąć przepisu, który był już publiczny)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-04 12:00:00.000000

Historia publikacji nie była dotąd zapisywana, więc dla istniejących przepisów
odtwarzamy ją z danych: oprócz opublikowanych za publiczne uznajemy przepisy
oczekujące/odrzucone, które mają komentarze, oceny lub wyświetlenia - te powstają
wyłącznie, gdy przepis jest opublikowany. Dokładna data pierwszej publikacji nie
jest znana, dlatego używamy daty utworzenia przepisu.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE recipes
        SET published_at = COALESCE(created_at, updated_at, CURRENT_TIMESTAMP)
        WHERE status = 'published'
           OR id IN (SELECT recipe_id FROM comments WHERE recipe_id IS NOT NULL)
           OR id IN (SELECT recipe_id FROM recipe_ratings)
           OR id IN (SELECT object_id FROM daily_views WHERE kind = 'recipe')
        """
    )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        # Jak w d4e5f6a7b8c9: przebudowa tabeli recipes byłaby blokowana przez klucze obce.
        op.execute("ALTER TABLE recipes DROP COLUMN published_at")
    else:
        op.drop_column('recipes', 'published_at')
