import re
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field, field_validator

from app.api.auth import get_current_user
from app.api.deps import (
    get_audit_collection,
    get_organization_collection,
    get_organization_member_collection,
    get_project_collection,
    get_project_member_collection,
)
from app.core.audit import record_audit_event
from app.core.pagination import sort_and_paginate
from app.core.rbac import require_organization_role
from app.models.domain import (
    OrganizationMemberModel,
    OrganizationModel,
    OrgRole,
    ProjectMemberModel,
    ProjectModel,
    ProjectRole,
)

router = APIRouter(tags=["organizations", "projects"])
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,49}$")
PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        slug = value.strip().lower().replace(" ", "-")
        if not SLUG_PATTERN.match(slug):
            raise ValueError("Slug must use lowercase letters, numbers, and hyphens")
        return slug


class AddOrganizationMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: OrgRole

    @field_validator("user_id")
    @classmethod
    def normalize_user_id(cls, value: str) -> str:
        return value.strip()


class CreateProjectRequest(BaseModel):
    key: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        key = value.strip().upper()
        if not PROJECT_KEY_PATTERN.match(key):
            raise ValueError("Project key must start with a letter and use A-Z0-9 only")
        return key

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class AddProjectMemberRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: ProjectRole

    @field_validator("user_id")
    @classmethod
    def normalize_user_id(cls, value: str) -> str:
        return value.strip()


def _serialize_org(doc: dict[str, Any]) -> OrganizationModel:
    return OrganizationModel(
        id=str(doc["_id"]),
        name=doc["name"],
        slug=doc["slug"],
        owner_user_id=str(doc["owner_user_id"]),
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat(),
    )


def _serialize_org_member(doc: dict[str, Any]) -> OrganizationMemberModel:
    return OrganizationMemberModel(
        id=str(doc["_id"]),
        organization_id=str(doc["organization_id"]),
        user_id=str(doc["user_id"]),
        role=doc["role"],
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat(),
    )


def _serialize_project(doc: dict[str, Any]) -> ProjectModel:
    return ProjectModel(
        id=str(doc["_id"]),
        organization_id=str(doc["organization_id"]),
        key=doc["key"],
        name=doc["name"],
        description=doc.get("description"),
        created_by_user_id=str(doc["created_by_user_id"]),
        issue_counter=doc.get("issue_counter", 0),
        archived=doc.get("archived", False),
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat(),
    )


def _serialize_project_member(doc: dict[str, Any]) -> ProjectMemberModel:
    return ProjectMemberModel(
        id=str(doc["_id"]),
        project_id=str(doc["project_id"]),
        user_id=str(doc["user_id"]),
        role=doc["role"],
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat(),
    )


@router.post(
    "/organizations",
    response_model=OrganizationModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    body: CreateOrganizationRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> OrganizationModel:
    existing = await organizations.find_one({"slug": body.slug})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    now = datetime.now(UTC)
    user_id = str(current_user["_id"])
    doc = {
        "name": body.name,
        "slug": body.slug,
        "owner_user_id": user_id,
        "created_at": now,
        "updated_at": now,
    }
    result = await organizations.insert_one(doc)
    organization_id = str(result.inserted_id)
    doc["_id"] = organization_id

    await organization_members.insert_one(
        {
            "organization_id": organization_id,
            "user_id": user_id,
            "role": OrgRole.OWNER.value,
            "created_at": now,
            "updated_at": now,
        }
    )
    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=user_id,
        event_type="organization.created",
        entity_type="organization",
        entity_id=organization_id,
        payload={"name": body.name, "slug": body.slug},
    )
    return _serialize_org(doc)


@router.get("/organizations", response_model=list[OrganizationModel])
async def list_organizations(
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "name", "slug"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> list[OrganizationModel]:
    user_id = str(current_user["_id"])
    org_docs = await organizations.find({}).to_list(length=2000)
    memberships = await organization_members.find({"user_id": user_id}).to_list(length=2000)
    member_org_ids = {str(item["organization_id"]) for item in memberships}

    visible = [
        doc
        for doc in org_docs
        if str(doc["owner_user_id"]) == user_id or str(doc["_id"]) in member_org_ids
    ]
    paged = sort_and_paginate(
        visible, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit
    )
    return [_serialize_org(doc) for doc in paged]


@router.post(
    "/organizations/{organization_id}/members",
    response_model=OrganizationMemberModel,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_member(
    organization_id: str,
    body: AddOrganizationMemberRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> OrganizationMemberModel:
    await require_organization_role(
        organization_id=organization_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, OrgRole.ADMIN.value},
        organizations=organizations,
        organization_members=organization_members,
    )
    if body.role == OrgRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner role is not assignable",
        )

    now = datetime.now(UTC)
    existing = await organization_members.find_one(
        {"organization_id": organization_id, "user_id": body.user_id}
    )
    if existing:
        await organization_members.update_one(
            {"_id": existing["_id"]},
            {"$set": {"role": body.role.value, "updated_at": now}},
        )
        merged = {**existing, "role": body.role.value, "updated_at": now}
        action = "organization_member.role_updated"
        model = _serialize_org_member(merged)
    else:
        doc = {
            "organization_id": organization_id,
            "user_id": body.user_id,
            "role": body.role.value,
            "created_at": now,
            "updated_at": now,
        }
        result = await organization_members.insert_one(doc)
        doc["_id"] = result.inserted_id
        action = "organization_member.added"
        model = _serialize_org_member(doc)

    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=str(current_user["_id"]),
        event_type=action,
        entity_type="organization_member",
        entity_id=model.id,
        payload={
            "organization_id": organization_id,
            "user_id": body.user_id,
            "role": body.role.value,
        },
    )
    return model


@router.get(
    "/organizations/{organization_id}/members",
    response_model=list[OrganizationMemberModel],
)
async def list_organization_members(
    organization_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "role", "user_id"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> list[OrganizationMemberModel]:
    await require_organization_role(
        organization_id=organization_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
    )
    docs = await organization_members.find(
        {"organization_id": organization_id}
    ).to_list(length=2000)
    paged = sort_and_paginate(
        docs, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit
    )
    return [_serialize_org_member(doc) for doc in paged]


@router.post(
    "/organizations/{organization_id}/projects",
    response_model=ProjectModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    organization_id: str,
    body: CreateProjectRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> ProjectModel:
    await require_organization_role(
        organization_id=organization_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, OrgRole.ADMIN.value},
        organizations=organizations,
        organization_members=organization_members,
    )

    existing = await projects.find_one(
        {"organization_id": organization_id, "key": body.key}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project key already exists",
        )

    now = datetime.now(UTC)
    user_id = str(current_user["_id"])
    doc = {
        "organization_id": organization_id,
        "key": body.key,
        "name": body.name,
        "description": body.description.strip() if body.description else None,
        "created_by_user_id": user_id,
        "issue_counter": 0,
        "archived": False,
        "created_at": now,
        "updated_at": now,
    }
    result = await projects.insert_one(doc)
    project_id = str(result.inserted_id)
    doc["_id"] = project_id

    project_member_result = await project_members.insert_one(
        {
            "project_id": project_id,
            "user_id": user_id,
            "role": ProjectRole.ADMIN.value,
            "created_at": now,
            "updated_at": now,
        }
    )
    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=user_id,
        event_type="project.created",
        entity_type="project",
        entity_id=project_id,
        payload={"organization_id": organization_id, "key": body.key, "name": body.name},
    )
    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=user_id,
        event_type="project_member.added",
        entity_type="project_member",
        entity_id=str(project_member_result.inserted_id),
        payload={"project_id": project_id, "user_id": user_id, "role": ProjectRole.ADMIN.value},
    )
    return _serialize_project(doc)


@router.get("/organizations/{organization_id}/projects", response_model=list[ProjectModel])
async def list_projects(
    organization_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "name", "key"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> list[ProjectModel]:
    await require_organization_role(
        organization_id=organization_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
    )
    docs = await projects.find({"organization_id": organization_id}).to_list(length=2000)
    paged = sort_and_paginate(
        docs, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit
    )
    return [_serialize_project(doc) for doc in paged]


@router.post("/projects/{project_id}/members", response_model=ProjectMemberModel, status_code=201)
async def add_project_member(
    project_id: str,
    body: AddProjectMemberRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> ProjectMemberModel:
    project = await projects.find_one({"_id": project_id})
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await require_organization_role(
        organization_id=project["organization_id"],
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, OrgRole.ADMIN.value},
        organizations=organizations,
        organization_members=organization_members,
    )

    now = datetime.now(UTC)
    existing = await project_members.find_one({"project_id": project_id, "user_id": body.user_id})
    if existing:
        await project_members.update_one(
            {"_id": existing["_id"]},
            {"$set": {"role": body.role.value, "updated_at": now}},
        )
        merged = {**existing, "role": body.role.value, "updated_at": now}
        action = "project_member.role_updated"
        model = _serialize_project_member(merged)
    else:
        doc = {
            "project_id": project_id,
            "user_id": body.user_id,
            "role": body.role.value,
            "created_at": now,
            "updated_at": now,
        }
        result = await project_members.insert_one(doc)
        doc["_id"] = result.inserted_id
        action = "project_member.added"
        model = _serialize_project_member(doc)

    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=str(current_user["_id"]),
        event_type=action,
        entity_type="project_member",
        entity_id=model.id,
        payload={"project_id": project_id, "user_id": body.user_id, "role": body.role.value},
    )
    return model


@router.get("/projects/{project_id}/members", response_model=list[ProjectMemberModel])
async def list_project_members(
    project_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "role", "user_id"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> list[ProjectMemberModel]:
    project = await projects.find_one({"_id": project_id})
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await require_organization_role(
        organization_id=project["organization_id"],
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
    )
    docs = await project_members.find({"project_id": project_id}).to_list(length=2000)
    paged = sort_and_paginate(
        docs, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit
    )
    return [_serialize_project_member(doc) for doc in paged]
