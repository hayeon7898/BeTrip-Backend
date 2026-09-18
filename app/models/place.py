from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class Place(Base):
    """DDL: places 테이블과 1:1 매칭"""

    __tablename__ = "places"

    place_id = Column(String(50), primary_key=True)  # Kakao Place ID 그대로 사용
    name = Column(String(200), nullable=False)
    category = Column(String(20), nullable=False)
    address = Column(String(300))
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    place_url = Column(Text)  # 카카오맵 상세 페이지 (웹뷰/iframe 임베드용)
    thumbnail_url = Column(Text)  # place_url의 og:image에서 가져온 값
    source = Column(String(20), nullable=False, server_default="KAKAO")
    source_synced_at = Column(TIMESTAMP)
    tags = Column(
        JSONB, nullable=False, server_default="[]"
    )  # 취향 태그 (예: ["감성", "루프탑"])
    tags_synced_at = Column(TIMESTAMP)  # 태그 마지막 갱신 시각 (재수집 판단용)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('RESTAURANT', 'CAFE', 'ACTIVITY')",
            name="chk_places_category",
        ),
        CheckConstraint(
            "source IN ('KAKAO', 'TOUR_API')",
            name="chk_places_source",
        ),
        Index("idx_places_category", "category"),
        Index("idx_places_name", "name"),
        Index(
            "idx_places_tags",
            "tags",
            postgresql_using="gin",
            postgresql_ops={"tags": "jsonb_path_ops"},
        ),
    )
