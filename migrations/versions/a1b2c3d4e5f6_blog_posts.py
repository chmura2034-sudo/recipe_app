"""blog posts

Revision ID: a1b2c3d4e5f6
Revises: 2573cf62cbfc
Create Date: 2026-11-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '2573cf62cbfc'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('blog_posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=150), nullable=False),
    sa.Column('slug', sa.String(length=180), nullable=False),
    sa.Column('excerpt', sa.String(length=300), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('image_url', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('blog_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_blog_posts_slug'), ['slug'], unique=True)
        batch_op.create_index(batch_op.f('ix_blog_posts_published_at'), ['published_at'], unique=False)


def downgrade():
    with op.batch_alter_table('blog_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blog_posts_published_at'))
        batch_op.drop_index(batch_op.f('ix_blog_posts_slug'))

    op.drop_table('blog_posts')
