"""add refresh_tokens indexes

Revision ID: 421c1867561a
Revises: 573461db6264
Create Date: 2026-09-19 21:10:23.433425

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "421c1867561a"
down_revision: Union[str, Sequence[str], None] = "573461db6264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_refresh_tokens_expires", "refresh_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "uq_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_refresh_tokens_hash", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_expires", table_name="refresh_tokens")
