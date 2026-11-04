"""previous_image_url (zatwierdzone zdjęcie czeka na decyzję o zmianach redaktora)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-04 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('recipes', 'blog_posts'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('previous_image_url', sa.String(length=500), nullable=True))


def downgrade():
    for table in ('recipes', 'blog_posts'):
        if op.get_bind().dialect.name == "sqlite":
            # Jak w d4e5f6a7b8c9: przebudowa tabeli byłaby blokowana przez klucze obce.
            op.execute(f"ALTER TABLE {table} DROP COLUMN previous_image_url")
        else:
            op.drop_column(table, 'previous_image_url')
