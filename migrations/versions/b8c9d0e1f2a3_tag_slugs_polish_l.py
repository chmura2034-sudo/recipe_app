"""tag slugs z literą ł ('masło' miało slug 'maso' zamiast 'maslo')

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-04 22:00:00.000000

Tagi są wyszukiwane po slugu wyliczanym z nazwy. Bez tej migracji po poprawce slugify
zapis przepisu z tagiem 'masło' próbowałby utworzyć go drugi raz i kończył się błędem
unikalności nazwy. Jeśli poprawny slug ma już inny tag, oba tagi są scalane.

Slugów przepisów i wpisów nie zmieniamy: są publicznymi adresami, a aplikacja nie ma
przekierowań ze starych adresów. Downgrade niczego nie cofa - scalania nie da się odwrócić.
"""
import re
import unicodedata

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def _slugify(text):
    # Kopia app.slugify - migracja nie może zależeć od przyszłych zmian w aplikacji.
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)


def upgrade():
    bind = op.get_bind()
    tags = sa.table('tags', sa.column('id', sa.Integer), sa.column('name', sa.String), sa.column('slug', sa.String))
    links = sa.table('recipe_tags', sa.column('recipe_id', sa.Integer), sa.column('tag_id', sa.Integer))

    for tag_id, name, slug in bind.execute(sa.select(tags.c.id, tags.c.name, tags.c.slug)).fetchall():
        if "ł" not in name.lower():
            continue
        new_slug = _slugify(name)
        if not new_slug or new_slug == slug:
            continue

        target_id = bind.execute(sa.select(tags.c.id).where(tags.c.slug == new_slug)).scalar()
        if target_id is None:
            bind.execute(tags.update().where(tags.c.id == tag_id).values(slug=new_slug))
            continue

        already_linked = sa.select(links.c.recipe_id).where(links.c.tag_id == target_id)
        bind.execute(
            links.update()
            .where(links.c.tag_id == tag_id, links.c.recipe_id.not_in(already_linked))
            .values(tag_id=target_id)
        )
        bind.execute(links.delete().where(links.c.tag_id == tag_id))
        bind.execute(tags.delete().where(tags.c.id == tag_id))


def downgrade():
    pass
