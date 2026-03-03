from motor.motor_asyncio import AsyncIOMotorCollection

from app.db.mongo import get_db


def get_user_collection() -> AsyncIOMotorCollection:
    return get_db()["users"]


def get_organization_collection() -> AsyncIOMotorCollection:
    return get_db()["organizations"]


def get_project_collection() -> AsyncIOMotorCollection:
    return get_db()["projects"]


def get_issue_collection() -> AsyncIOMotorCollection:
    return get_db()["issues"]


def get_comment_collection() -> AsyncIOMotorCollection:
    return get_db()["comments"]


def get_organization_member_collection() -> AsyncIOMotorCollection:
    return get_db()["organization_members"]


def get_project_member_collection() -> AsyncIOMotorCollection:
    return get_db()["project_members"]


def get_audit_collection() -> AsyncIOMotorCollection:
    return get_db()["audit_events"]
