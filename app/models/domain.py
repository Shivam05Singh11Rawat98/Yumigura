from enum import StrEnum

from pydantic import BaseModel


class OrgRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class ProjectRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class IssueType(StrEnum):
    BUG = "Bug"
    TASK = "Task"
    STORY = "Story"


class IssuePriority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class IssueStatus(StrEnum):
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class OrganizationModel(BaseModel):
    id: str
    name: str
    slug: str
    owner_user_id: str
    created_at: str
    updated_at: str


class ProjectModel(BaseModel):
    id: str
    organization_id: str
    key: str
    name: str
    description: str | None
    created_by_user_id: str
    issue_counter: int
    archived: bool
    created_at: str
    updated_at: str


class IssueModel(BaseModel):
    id: str
    organization_id: str
    project_id: str
    issue_key: str
    title: str
    description: str | None
    issue_type: str
    status: str
    priority: str
    reporter_user_id: str
    assignee_user_id: str | None
    labels: list[str]
    created_at: str
    updated_at: str
    deleted_at: str | None


class CommentModel(BaseModel):
    id: str
    issue_id: str
    author_user_id: str
    body: str
    created_at: str
    updated_at: str
    deleted_at: str | None


class OrganizationMemberModel(BaseModel):
    id: str
    organization_id: str
    user_id: str
    role: str
    created_at: str
    updated_at: str


class ProjectMemberModel(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: str
    created_at: str
    updated_at: str
