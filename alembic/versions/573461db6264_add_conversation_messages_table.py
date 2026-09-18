"""add conversation_messages table

Revision ID: 573461db6264
Revises: 1c492a7faa60
Create Date: 2026-09-16 21:56:55.872889

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "573461db6264"
down_revision: Union[str, Sequence[str], None] = "1c492a7faa60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column(
            "message_id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "itinerary_id",
            sa.UUID(),
            sa.ForeignKey("itineraries.itinerary_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "chk_conversation_messages_role",
        "conversation_messages",
        "role IN ('user', 'assistant')",
    )
    op.create_index(
        "idx_conversation_messages_itinerary",
        "conversation_messages",
        ["itinerary_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_conversation_messages_itinerary", "conversation_messages")
    op.drop_constraint("chk_conversation_messages_role", "conversation_messages")
    op.drop_table("conversation_messages")
