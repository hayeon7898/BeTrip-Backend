"""itinerary_places 스케줄 컬럼 nullable + 슬롯 unique 추가

Revision ID: e467eebb8b73
Revises: 51be991c8090
Create Date: 2026-08-12 06:05:27.149254

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "e467eebb8b73"
down_revision: Union[str, Sequence[str], None] = "51be991c8090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
