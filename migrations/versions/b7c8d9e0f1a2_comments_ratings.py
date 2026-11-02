"""comments and recipe ratings

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-11-02 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=True),
    sa.Column('blog_post_id', sa.Integer(), nullable=True),
    sa.Column('author_name', sa.String(length=60), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('voter_hash', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('(recipe_id IS NULL) <> (blog_post_id IS NULL)', name='ck_comments_one_target'),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['blog_post_id'], ['blog_posts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_comments_recipe_id'), ['recipe_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_blog_post_id'), ['blog_post_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_status'), ['status'], unique=False)

    op.create_table('recipe_ratings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('voter_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('score BETWEEN 1 AND 5', name='ck_recipe_ratings_score'),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('recipe_id', 'voter_hash', name='uq_recipe_ratings_voter')
    )
    with op.batch_alter_table('recipe_ratings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recipe_ratings_recipe_id'), ['recipe_id'], unique=False)


def downgrade():
    with op.batch_alter_table('recipe_ratings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recipe_ratings_recipe_id'))
    op.drop_table('recipe_ratings')

    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_comments_status'))
        batch_op.drop_index(batch_op.f('ix_comments_blog_post_id'))
        batch_op.drop_index(batch_op.f('ix_comments_recipe_id'))
    op.drop_table('comments')
