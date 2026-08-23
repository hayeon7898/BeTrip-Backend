"""make itinerary_places schedule columns nullable, add slot unique constraint

Revision ID: e467eebb8b73
Revises: 51be991c8090
Create Date: 2026-08-12 06:05:27.149254

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e467eebb8b73"
down_revision: Union[str, Sequence[str], None] = "51be991c8090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # day/time_slot/order_in_day를 nullable로 변경
    # (담기만 하고 아직 일자 미배정인 상태를 허용하기 위함)
    op.alter_column("itinerary_places", "day", nullable=True)
    op.alter_column("itinerary_places", "time_slot", nullable=True)
    op.alter_column("itinerary_places", "order_in_day", nullable=True)

    # 같은 슬롯(day, time_slot, order_in_day)에 중복 배정 방지
    # 단, day가 NULL(미배정)인 담기 상태는 여러 개 허용되어야 하므로
    # 부분 unique index로 제한
    op.execute(
        """
        CREATE UNIQUE INDEX uq_itinerary_places_slot
        ON itinerary_places (itinerary_id, day, time_slot, order_in_day)
        WHERE day IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_itinerary_places_slot")
    op.alter_column("itinerary_places", "order_in_day", nullable=False)
    op.alter_column("itinerary_places", "time_slot", nullable=False)
    op.alter_column("itinerary_places", "day", nullable=False)
