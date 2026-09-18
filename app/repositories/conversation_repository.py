from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_message import ConversationMessage


class ConversationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_history(self, itinerary_id: str) -> list[ConversationMessage]:
        """시간순 전체 대화 히스토리 조회. Gemini Chat 세션 복원용."""
        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.itinerary_id == itinerary_id)
            .order_by(ConversationMessage.created_at)
        )
        return list(result.scalars().all())

    async def add_message(
        self, itinerary_id: str, role: str, content: str
    ) -> ConversationMessage:
        message = ConversationMessage(
            itinerary_id=itinerary_id, role=role, content=content
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message
