from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.models.domain import OrgRole, ProjectRole


async def get_organization_role(
    organization_id: str,
    user_id: str,
    organizations: AsyncIOMotorCollection,
    organization_members: AsyncIOMotorCollection,
) -> str | None:
    organization = await organizations.find_one({"_id": organization_id})
    if organization is None:
        return None

    if organization["owner_user_id"] == user_id:
        return OrgRole.OWNER.value

    membership = await organization_members.find_one(
        {"organization_id": organization_id, "user_id": user_id}
    )
    if membership is None:
        return None
    return membership["role"]


async def require_organization_role(
    organization_id: str,
    user_id: str,
    allowed_roles: set[str],
    organizations: AsyncIOMotorCollection,
    organization_members: AsyncIOMotorCollection,
) -> dict:
    organization = await organizations.find_one({"_id": organization_id})
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    role = await get_organization_role(
        organization_id=organization_id,
        user_id=user_id,
        organizations=organizations,
        organization_members=organization_members,
    )
    if role is None or role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return organization


async def get_project_role(
    project_id: str,
    user_id: str,
    organizations: AsyncIOMotorCollection,
    organization_members: AsyncIOMotorCollection,
    projects: AsyncIOMotorCollection,
    project_members: AsyncIOMotorCollection,
) -> tuple[dict | None, str | None]:
    project = await projects.find_one({"_id": project_id})
    if project is None:
        return None, None

    org_role = await get_organization_role(
        organization_id=project["organization_id"],
        user_id=user_id,
        organizations=organizations,
        organization_members=organization_members,
    )
    if org_role == OrgRole.OWNER.value:
        return project, OrgRole.OWNER.value
    if org_role == OrgRole.ADMIN.value:
        return project, ProjectRole.ADMIN.value

    membership = await project_members.find_one({"project_id": project_id, "user_id": user_id})
    if membership is None:
        return project, None
    return project, membership["role"]


async def require_project_role(
    project_id: str,
    user_id: str,
    allowed_roles: set[str],
    organizations: AsyncIOMotorCollection,
    organization_members: AsyncIOMotorCollection,
    projects: AsyncIOMotorCollection,
    project_members: AsyncIOMotorCollection,
) -> dict:
    project, role = await get_project_role(
        project_id=project_id,
        user_id=user_id,
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if role is None or role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return project
