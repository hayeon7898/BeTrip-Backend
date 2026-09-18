from enum import Enum

from pydantic import BaseModel


class PlaceTag(str, Enum):
    EMOTIONAL = "감성"
    QUIET = "조용함"
    VIEW = "뷰맛집"
    ROOFTOP = "루프탑"
    PHOTO_SPOT = "인생샷"
    DATE = "데이트"
    FAMILY = "가족"
    PET_FRIENDLY = "반려동물동반"
    HIP = "힙함"
    VINTAGE = "빈티지"
    WAITING = "대기줄있음"


class TagClassificationResult(BaseModel):
    tags: list[PlaceTag]
