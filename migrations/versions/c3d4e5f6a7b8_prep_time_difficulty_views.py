"""recipe prep time, difficulty and daily view counters

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-11-02 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prep_time_min', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('difficulty', sa.String(length=20), nullable=True))

    op.create_table('daily_views',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('object_id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('views', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('kind', 'object_id', 'day', name='uq_daily_views')
    )
    with op.batch_alter_table('daily_views', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_daily_views_day'), ['day'], unique=False)


def downgrade():
    with op.batch_alter_table('daily_views', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_daily_views_day'))
    op.drop_table('daily_views')

    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_column('difficulty')
        batch_op.drop_column('prep_time_min')
