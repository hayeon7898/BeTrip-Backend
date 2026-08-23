"""add tags to places

Revision ID: 1c492a7faa60
Revises: e467eebb8b73
Create Date: 2026-08-23 16:50:07.745929

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c492a7faa60"
down_revision: Union[str, Sequence[str], None] = "e467eebb8b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "places",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "places",
        sa.Column("tags_synced_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_check_constraint(
        "chk_places_source",
        "places",
        "source IN ('KAKAO', 'TOUR_API')",
    )
    op.execute("CREATE INDEX idx_places_tags ON places USING GIN (tags jsonb_path_ops)")


def downgrade():
    op.execute("DROP INDEX idx_places_tags")
    op.drop_constraint("chk_places_source", "places")
    op.drop_column("places", "tags_synced_at")
    op.drop_column("places", "tags")
