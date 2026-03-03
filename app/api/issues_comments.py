from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.auth import get_current_user
from app.api.deps import (
    get_audit_collection,
    get_comment_collection,
    get_issue_collection,
    get_organization_collection,
    get_organization_member_collection,
    get_project_collection,
    get_project_member_collection,
)
from app.core.audit import record_audit_event
from app.core.pagination import sort_and_paginate
from app.core.rbac import require_project_role
from app.models.domain import (
    CommentModel,
    IssueModel,
    IssuePriority,
    IssueStatus,
    IssueType,
    OrgRole,
    ProjectRole,
)

router = APIRouter(tags=["issues", "comments"])


class CreateIssueRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    issue_type: IssueType
    priority: IssuePriority
    assignee_user_id: str | None = None
    labels: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: list[str]) -> list[str]:
        normalized = [label.strip().lower() for label in value if label.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Labels must be unique")
        if any(len(label) > 40 for label in normalized):
            raise ValueError("Each label must be at most 40 characters")
        return normalized


class UpdateIssueRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    issue_type: IssueType | None = None
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    assignee_user_id: str | None = None
    labels: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_has_updates(self) -> "UpdateIssueRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update")
        return self

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = [label.strip().lower() for label in value if label.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Labels must be unique")
        if any(len(label) > 40 for label in normalized):
            raise ValueError("Each label must be at most 40 characters")
        return normalized


class CreateCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=3000)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        return value.strip()


def _serialize_issue(doc: dict[str, Any]) -> IssueModel:
    return IssueModel(
        id=str(doc["_id"]),
        organization_id=str(doc["organization_id"]),
        project_id=str(doc["project_id"]),
        issue_key=doc["issue_key"],
        title=doc["title"],
        description=doc.get("description"),
        issue_type=doc["issue_type"],
        status=doc["status"],
        priority=doc["priority"],
        reporter_user_id=str(doc["reporter_user_id"]),
        assignee_user_id=doc.get("assignee_user_id"),
        labels=doc.get("labels", []),
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat(),
        deleted_at=doc["deleted_at"].isoformat() if doc.get("deleted_at") else None,
    )


def _serialize_comment(doc: dict[str, Any]) -> CommentModel:
    return CommentModel(
        id=str(doc["_id"]),
        issue_id=str(doc["issue_id"]),
        author_user_id=str(doc["author_user_id"]),
        body=doc["body"],
        created_at=doc["created_at"].isoformat(),
        updated_at=doc["updated_at"].isoformat(),
        deleted_at=doc["deleted_at"].isoformat() if doc.get("deleted_at") else None,
    )


@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_issue(
    project_id: str,
    body: CreateIssueRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> IssueModel:
    project = await require_project_role(
        project_id=project_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value, ProjectRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )

    now = datetime.now(UTC)
    next_counter = int(project.get("issue_counter", 0)) + 1
    await projects.update_one(
        {"_id": project_id},
        {"$set": {"issue_counter": next_counter, "updated_at": now}},
    )

    doc = {
        "organization_id": project["organization_id"],
        "project_id": project_id,
        "issue_key": f"{project['key']}-{next_counter}",
        "title": body.title,
        "description": body.description,
        "issue_type": body.issue_type.value,
        "status": IssueStatus.TODO.value,
        "priority": body.priority.value,
        "reporter_user_id": str(current_user["_id"]),
        "assignee_user_id": body.assignee_user_id,
        "labels": body.labels,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    result = await issues.insert_one(doc)
    doc["_id"] = result.inserted_id
    issue_model = _serialize_issue(doc)

    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=str(current_user["_id"]),
        event_type="issue.created",
        entity_type="issue",
        entity_id=issue_model.id,
        payload={
            "project_id": project_id,
            "issue_key": issue_model.issue_key,
            "issue_type": issue_model.issue_type,
            "priority": issue_model.priority,
        },
    )
    return issue_model


@router.get("/projects/{project_id}/issues", response_model=list[IssueModel])
async def list_issues(
    project_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    assignee_user_id: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at", "issue_key", "priority", "status"] = Query(
        default="created_at"
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
) -> list[IssueModel]:
    await require_project_role(
        project_id=project_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value, ProjectRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )

    query: dict[str, Any] = {"project_id": project_id, "deleted_at": None}
    if status_filter:
        query["status"] = status_filter
    if assignee_user_id:
        query["assignee_user_id"] = assignee_user_id
    if issue_type:
        query["issue_type"] = issue_type
    if priority:
        query["priority"] = priority

    docs = await issues.find(query).to_list(length=3000)
    paged = sort_and_paginate(
        docs, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit
    )
    return [_serialize_issue(doc) for doc in paged]


@router.get("/projects/{project_id}/issues/{issue_id}", response_model=IssueModel)
async def get_issue(
    project_id: str,
    issue_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
) -> IssueModel:
    await require_project_role(
        project_id=project_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value, ProjectRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )
    issue = await issues.find_one({"_id": issue_id, "project_id": project_id, "deleted_at": None})
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return _serialize_issue(issue)


@router.patch("/projects/{project_id}/issues/{issue_id}", response_model=IssueModel)
async def update_issue(
    project_id: str,
    issue_id: str,
    body: UpdateIssueRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> IssueModel:
    await require_project_role(
        project_id=project_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )
    issue = await issues.find_one({"_id": issue_id, "project_id": project_id, "deleted_at": None})
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    update_fields = body.model_dump(exclude_unset=True)
    if "issue_type" in update_fields and update_fields["issue_type"] is not None:
        update_fields["issue_type"] = update_fields["issue_type"].value
    if "status" in update_fields and update_fields["status"] is not None:
        update_fields["status"] = update_fields["status"].value
    if "priority" in update_fields and update_fields["priority"] is not None:
        update_fields["priority"] = update_fields["priority"].value
    update_fields["updated_at"] = datetime.now(UTC)

    await issues.update_one({"_id": issue_id}, {"$set": update_fields})
    merged = {**issue, **update_fields}
    issue_model = _serialize_issue(merged)

    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=str(current_user["_id"]),
        event_type="issue.updated",
        entity_type="issue",
        entity_id=issue_model.id,
        payload={"updated_fields": sorted(update_fields.keys())},
    )
    return issue_model


@router.delete("/projects/{project_id}/issues/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(
    project_id: str,
    issue_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
    audit_events: AsyncIOMotorCollection = Depends(get_audit_collection),
) -> None:
    await require_project_role(
        project_id=project_id,
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )
    issue = await issues.find_one({"_id": issue_id, "project_id": project_id, "deleted_at": None})
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    now = datetime.now(UTC)
    await issues.update_one({"_id": issue_id}, {"$set": {"deleted_at": now, "updated_at": now}})
    await record_audit_event(
        audit_events=audit_events,
        actor_user_id=str(current_user["_id"]),
        event_type="issue.deleted",
        entity_type="issue",
        entity_id=issue_id,
        payload={"project_id": project_id},
    )


@router.post(
    "/issues/{issue_id}/comments",
    response_model=CommentModel,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    issue_id: str,
    body: CreateCommentRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
    comments: AsyncIOMotorCollection = Depends(get_comment_collection),
) -> CommentModel:
    issue = await issues.find_one({"_id": issue_id, "deleted_at": None})
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    await require_project_role(
        project_id=issue["project_id"],
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value, ProjectRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )

    now = datetime.now(UTC)
    doc = {
        "issue_id": issue_id,
        "author_user_id": str(current_user["_id"]),
        "body": body.body,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    result = await comments.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize_comment(doc)


@router.get("/issues/{issue_id}/comments", response_model=list[CommentModel])
async def list_comments(
    issue_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "updated_at"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    current_user: dict[str, Any] = Depends(get_current_user),
    organizations: AsyncIOMotorCollection = Depends(get_organization_collection),
    organization_members: AsyncIOMotorCollection = Depends(get_organization_member_collection),
    projects: AsyncIOMotorCollection = Depends(get_project_collection),
    project_members: AsyncIOMotorCollection = Depends(get_project_member_collection),
    issues: AsyncIOMotorCollection = Depends(get_issue_collection),
    comments: AsyncIOMotorCollection = Depends(get_comment_collection),
) -> list[CommentModel]:
    issue = await issues.find_one({"_id": issue_id, "deleted_at": None})
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    await require_project_role(
        project_id=issue["project_id"],
        user_id=str(current_user["_id"]),
        allowed_roles={OrgRole.OWNER.value, ProjectRole.ADMIN.value, ProjectRole.MEMBER.value},
        organizations=organizations,
        organization_members=organization_members,
        projects=projects,
        project_members=project_members,
    )
    docs = await comments.find({"issue_id": issue_id, "deleted_at": None}).to_list(length=3000)
    paged = sort_and_paginate(
        docs, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit
    )
    return [_serialize_comment(doc) for doc in paged]
