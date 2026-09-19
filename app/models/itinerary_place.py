import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItineraryPlace(Base):
    """
    일정에 "담긴 장소"와 "스케줄 아이템"을 겸용하는 테이블.

    담기(POST) 시점에는 day/time_slot/order_in_day가 NULL(스케줄 미배치)
    상태로 생성되고, 이후 스케줄 배치 기능에서 값이 채워진다.
    """

    __tablename__ = "itinerary_places"
    __table_args__ = (
        CheckConstraint(
            "time_slot IN ('MORNING', 'LUNCH', 'EVENING')",
            name="chk_itinerary_places_time_slot",
        ),
        CheckConstraint("day >= 1", name="chk_itinerary_places_day"),
        UniqueConstraint("itinerary_id", "place_id", name="uq_itinerary_places_place"),
        # 정렬 조회용 인덱스
        # (실제 DB에 존재하므로 모델에도 선언해 autogenerate 불일치 방지)
        Index(
            "idx_itinerary_places_order",
            "itinerary_id",
            "day",
            "time_slot",
            "order_in_day",
        ),
        # 배치된 행(day IS NOT NULL)만 슬롯 중복을 막는 부분 유니크 인덱스.
        # 같은 이름의 UniqueConstraint를 함께 선언하면 빈 DB에서 create_all 시
        # DuplicateTableError가 나므로 이 Index 하나만 유지한다.
        Index(
            "uq_itinerary_places_slot",
            "itinerary_id",
            "day",
            "time_slot",
            "order_in_day",
            unique=True,
            postgresql_where=text("day IS NOT NULL"),
        ),
    )

    itinerary_place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    itinerary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("itineraries.itinerary_id", ondelete="CASCADE"),
        nullable=False,
    )
    place_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("places.place_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 담기(POST) 시점에는 NULL, 스케줄 배치 시 값이 채워짐
    day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    time_slot: Mapped[str | None] = mapped_column(String(10), nullable=True)
    order_in_day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    travel_time_to_next_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
