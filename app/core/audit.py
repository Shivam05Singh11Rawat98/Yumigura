from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection


async def record_audit_event(
    *,
    audit_events: AsyncIOMotorCollection,
    actor_user_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await audit_events.insert_one(
        {
            "actor_user_id": actor_user_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload or {},
            "created_at": datetime.now(UTC),
        }
    )
