import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
logger = logging.getLogger(__name__)


async def connect_to_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(settings.mongodb_url)
    _db = _client[settings.mongodb_db_name]
    summary = await ensure_indexes(_db)
    logger.info(
        (
            "Mongo index initialization complete: users=%d organizations=%d "
            "organization_members=%d projects=%d project_members=%d issues=%d "
            "comments=%d audit_events=%d total=%d"
        ),
        summary["users"],
        summary["organizations"],
        summary["organization_members"],
        summary["projects"],
        summary["project_members"],
        summary["issues"],
        summary["comments"],
        summary["audit_events"],
        summary["total"],
    )


async def ensure_indexes(db: AsyncIOMotorDatabase) -> dict[str, int]:
    counts: dict[str, int] = {
        "users": 0,
        "organizations": 0,
        "organization_members": 0,
        "projects": 0,
        "project_members": 0,
        "issues": 0,
        "comments": 0,
        "audit_events": 0,
        "total": 0,
    }

    await db["users"].create_index(
        [("email", ASCENDING)],
        unique=True,
        name="uq_users_email",
    )
    counts["users"] += 1

    await db["organizations"].create_index(
        [("slug", ASCENDING)],
        unique=True,
        name="uq_organizations_slug",
    )
    counts["organizations"] += 1
    await db["organizations"].create_index(
        [("owner_user_id", ASCENDING)],
        name="idx_organizations_owner_user_id",
    )
    counts["organizations"] += 1

    await db["organization_members"].create_index(
        [("organization_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="uq_organization_members_org_user",
    )
    counts["organization_members"] += 1
    await db["organization_members"].create_index(
        [("user_id", ASCENDING)],
        name="idx_organization_members_user_id",
    )
    counts["organization_members"] += 1

    await db["projects"].create_index(
        [("organization_id", ASCENDING), ("key", ASCENDING)],
        unique=True,
        name="uq_projects_org_key",
    )
    counts["projects"] += 1
    await db["projects"].create_index(
        [("organization_id", ASCENDING)],
        name="idx_projects_organization_id",
    )
    counts["projects"] += 1

    await db["project_members"].create_index(
        [("project_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="uq_project_members_project_user",
    )
    counts["project_members"] += 1
    await db["project_members"].create_index(
        [("user_id", ASCENDING)],
        name="idx_project_members_user_id",
    )
    counts["project_members"] += 1

    await db["issues"].create_index(
        [("project_id", ASCENDING), ("issue_key", ASCENDING)],
        unique=True,
        name="uq_issues_project_issue_key",
    )
    counts["issues"] += 1
    await db["issues"].create_index(
        [("project_id", ASCENDING), ("status", ASCENDING)],
        name="idx_issues_project_status",
    )
    counts["issues"] += 1
    await db["issues"].create_index(
        [("project_id", ASCENDING), ("assignee_user_id", ASCENDING)],
        name="idx_issues_project_assignee",
    )
    counts["issues"] += 1
    await db["issues"].create_index(
        [("labels", ASCENDING)],
        name="idx_issues_labels",
    )
    counts["issues"] += 1
    await db["issues"].create_index(
        [("project_id", ASCENDING), ("deleted_at", ASCENDING)],
        name="idx_issues_project_deleted_at",
    )
    counts["issues"] += 1

    await db["comments"].create_index(
        [("issue_id", ASCENDING), ("deleted_at", ASCENDING)],
        name="idx_comments_issue_deleted_at",
    )
    counts["comments"] += 1
    await db["comments"].create_index(
        [("author_user_id", ASCENDING)],
        name="idx_comments_author_user_id",
    )
    counts["comments"] += 1

    await db["audit_events"].create_index(
        [("entity_type", ASCENDING), ("entity_id", ASCENDING), ("created_at", ASCENDING)],
        name="idx_audit_entity_created_at",
    )
    counts["audit_events"] += 1
    await db["audit_events"].create_index(
        [("actor_user_id", ASCENDING), ("created_at", ASCENDING)],
        name="idx_audit_actor_created_at",
    )
    counts["audit_events"] += 1

    counts["total"] = (
        counts["users"]
        + counts["organizations"]
        + counts["organization_members"]
        + counts["projects"]
        + counts["project_members"]
        + counts["issues"]
        + counts["comments"]
        + counts["audit_events"]
    )
    return counts


async def close_mongo_connection() -> None:
    global _client
    if _client:
        _client.close()


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db
