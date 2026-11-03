"""user session token (unieważnianie sesji po zmianie hasła / wylogowaniu)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-03 12:00:00.000000

Istniejące sesje mają stary format identyfikatora, więc po tej migracji wszyscy
zalogowani użytkownicy muszą zalogować się ponownie (znacznik powstaje przy logowaniu).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_token', sa.String(length=64), nullable=True))


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        # Tryb "batch" przebudowałby całą tabelę users, co przy włączonych kluczach obcych
        # (PRAGMA foreign_keys=ON) blokują przepisy/wpisy wskazujące na autora.
        # Kolumna nie ma indeksów ani ograniczeń, więc wystarczy natywny DROP COLUMN (SQLite >= 3.35).
        op.execute("ALTER TABLE users DROP COLUMN session_token")
    else:
        op.drop_column('users', 'session_token')
