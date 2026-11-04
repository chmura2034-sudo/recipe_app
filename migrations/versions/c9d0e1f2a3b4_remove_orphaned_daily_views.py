"""Usunięcie wyświetleń po skasowanych przepisach i wpisach

DailyView nie ma klucza obcego, a SQLite używa ponownie zwolnionych id, więc nowa
treść mogła przejąć takie wiersze. Aplikacja kasuje je już razem z treścią, ta migracja
czyści to, co zostało wcześniej. Nie da się odróżnić wierszy, które zdążyły już przejść
na nową treść o tym samym id - te zostają.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-04 23:30:00.000000
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "DELETE FROM daily_views WHERE kind = 'recipe' AND object_id NOT IN (SELECT id FROM recipes)"
    )
    op.execute(
        "DELETE FROM daily_views WHERE kind = 'blog' AND object_id NOT IN (SELECT id FROM blog_posts)"
    )


def downgrade():
    # Skasowanych wierszy nie da się odtworzyć, a schemat się nie zmienił.
    pass
