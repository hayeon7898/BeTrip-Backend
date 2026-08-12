from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.itinerary import ItineraryStatus, ScheduleResponse


class PlanGenerateResponse(BaseModel):
    itinerary_id: UUID
    status: ItineraryStatus
    schedule: ScheduleResponse | None


class PlanSaveResponse(BaseModel):
    itinerary_id: UUID
    status: ItineraryStatus
    saved_at: datetime
