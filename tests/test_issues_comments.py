from fastapi.testclient import TestClient

from app.api.deps import (
    get_audit_collection,
    get_comment_collection,
    get_issue_collection,
    get_organization_collection,
    get_organization_member_collection,
    get_project_collection,
    get_project_member_collection,
    get_user_collection,
)
from app.main import app


class FakeInsertResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def to_list(self, length: int) -> list[dict]:
        return self._docs[:length]


class FakeCollection:
    def __init__(self) -> None:
        self._items: dict[str, dict] = {}

    async def find_one(self, query: dict) -> dict | None:
        for item in self._items.values():
            if all(item.get(k) == v for k, v in query.items()):
                return item
        return None

    async def insert_one(self, document: dict) -> FakeInsertResult:
        inserted_id = str(len(self._items) + 1)
        self._items[inserted_id] = {"_id": inserted_id, **document}
        return FakeInsertResult(inserted_id)

    def find(self, query: dict) -> FakeCursor:
        docs = [
            item
            for item in self._items.values()
            if all(item.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(docs)

    async def update_one(self, query: dict, update: dict) -> None:
        item = await self.find_one(query)
        if item is None:
            return
        set_fields = update.get("$set", {})
        for key, value in set_fields.items():
            item[key] = value


def _make_client() -> tuple[
    TestClient,
    FakeCollection,
    FakeCollection,
    FakeCollection,
    FakeCollection,
    FakeCollection,
    FakeCollection,
    FakeCollection,
]:
    users = FakeCollection()
    organizations = FakeCollection()
    organization_members = FakeCollection()
    projects = FakeCollection()
    project_members = FakeCollection()
    issues = FakeCollection()
    comments = FakeCollection()
    audit_events = FakeCollection()

    app.dependency_overrides[get_user_collection] = lambda: users
    app.dependency_overrides[get_organization_collection] = lambda: organizations
    app.dependency_overrides[get_organization_member_collection] = lambda: organization_members
    app.dependency_overrides[get_project_collection] = lambda: projects
    app.dependency_overrides[get_project_member_collection] = lambda: project_members
    app.dependency_overrides[get_issue_collection] = lambda: issues
    app.dependency_overrides[get_comment_collection] = lambda: comments
    app.dependency_overrides[get_audit_collection] = lambda: audit_events
    return (
        TestClient(app),
        users,
        organizations,
        organization_members,
        projects,
        project_members,
        issues,
        comments,
        audit_events,
    )


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


def _auth_headers(client: TestClient, email: str) -> dict[str, str]:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPass123"},
    )
    token = register.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_org_and_project(
    client: TestClient, headers: dict[str, str], slug: str
) -> tuple[str, str]:
    org = client.post(
        "/api/v1/organizations",
        json={"name": "Issue Org", "slug": slug},
        headers=headers,
    ).json()
    project = client.post(
        f"/api/v1/organizations/{org['id']}/projects",
        json={"key": "YUM", "name": "Yumigura Project"},
        headers=headers,
    ).json()
    return org["id"], project["id"]


def test_issue_crud_and_soft_delete_flow() -> None:
    client, *_ = _make_client()
    headers = _auth_headers(client, "owner-issue@example.com")
    _, project_id = _create_org_and_project(client, headers, "issue-org")

    create = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={
            "title": "Cannot login",
            "description": "Login returns 500",
            "issue_type": "Bug",
            "priority": "High",
            "labels": ["auth", "backend"],
        },
        headers=headers,
    )
    assert create.status_code == 201
    issue = create.json()
    issue_id = issue["id"]
    assert issue["issue_key"] == "YUM-1"
    assert issue["status"] == "To Do"

    update = client.patch(
        f"/api/v1/projects/{project_id}/issues/{issue_id}",
        json={"status": "In Progress", "priority": "Critical"},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["status"] == "In Progress"

    delete = client.delete(f"/api/v1/projects/{project_id}/issues/{issue_id}", headers=headers)
    assert delete.status_code == 204

    get_deleted = client.get(f"/api/v1/projects/{project_id}/issues/{issue_id}", headers=headers)
    _cleanup_overrides()
    assert get_deleted.status_code == 404


def test_comments_flow() -> None:
    client, *_ = _make_client()
    headers = _auth_headers(client, "owner-comments@example.com")
    _, project_id = _create_org_and_project(client, headers, "comment-org")

    issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"title": "Comment test", "issue_type": "Task", "priority": "Medium"},
        headers=headers,
    ).json()

    add_comment = client.post(
        f"/api/v1/issues/{issue['id']}/comments",
        json={"body": "Working on this now"},
        headers=headers,
    )
    assert add_comment.status_code == 201

    listing = client.get(f"/api/v1/issues/{issue['id']}/comments", headers=headers)
    _cleanup_overrides()

    assert listing.status_code == 200
    comments = listing.json()
    assert len(comments) == 1
    assert comments[0]["body"] == "Working on this now"


def test_project_member_can_read_and_create_but_not_delete() -> None:
    client, *_ = _make_client()
    owner_headers = _auth_headers(client, "owner-rbac@example.com")
    member_headers = _auth_headers(client, "member-rbac@example.com")
    org_id, project_id = _create_org_and_project(client, owner_headers, "rbac-org")

    member_user = client.get("/api/v1/auth/me", headers=member_headers).json()
    add_member = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": member_user["id"], "role": "member"},
        headers=owner_headers,
    )
    assert add_member.status_code == 201

    create_issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"title": "Member issue", "issue_type": "Story", "priority": "Low"},
        headers=member_headers,
    )
    assert create_issue.status_code == 201
    issue_id = create_issue.json()["id"]

    read_issue = client.get(
        f"/api/v1/projects/{project_id}/issues/{issue_id}", headers=member_headers
    )
    assert read_issue.status_code == 200

    delete_issue = client.delete(
        f"/api/v1/projects/{project_id}/issues/{issue_id}", headers=member_headers
    )
    _cleanup_overrides()

    assert org_id is not None
    assert delete_issue.status_code == 403
    assert delete_issue.json()["error"]["message"] == "Not allowed"


def test_non_member_cannot_access_project_issues() -> None:
    client, *_ = _make_client()
    owner_headers = _auth_headers(client, "owner-forbidden@example.com")
    other_headers = _auth_headers(client, "other-forbidden@example.com")
    _, project_id = _create_org_and_project(client, owner_headers, "forbidden-org")

    forbidden = client.get(f"/api/v1/projects/{project_id}/issues", headers=other_headers)
    _cleanup_overrides()

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["message"] == "Not allowed"


def test_issue_list_supports_sort_pagination_and_filters() -> None:
    client, *_ = _make_client()
    headers = _auth_headers(client, "owner-sort@example.com")
    _, project_id = _create_org_and_project(client, headers, "sort-org")

    client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"title": "B issue", "issue_type": "Bug", "priority": "Low"},
        headers=headers,
    )
    client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"title": "A issue", "issue_type": "Task", "priority": "High"},
        headers=headers,
    )

    response = client.get(
        f"/api/v1/projects/{project_id}/issues",
        params={"sort_by": "issue_key", "sort_order": "asc", "limit": 1, "offset": 1},
        headers=headers,
    )
    _cleanup_overrides()

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["issue_key"] == "YUM-2"


def test_update_issue_requires_non_empty_body_and_records_audit() -> None:
    client, _, _, _, _, _, _, _, audit_events = _make_client()
    headers = _auth_headers(client, "owner-audit@example.com")
    _, project_id = _create_org_and_project(client, headers, "audit-issues-org")

    issue = client.post(
        f"/api/v1/projects/{project_id}/issues",
        json={"title": "Needs updates", "issue_type": "Task", "priority": "Medium"},
        headers=headers,
    ).json()

    empty_update = client.patch(
        f"/api/v1/projects/{project_id}/issues/{issue['id']}",
        json={},
        headers=headers,
    )
    valid_update = client.patch(
        f"/api/v1/projects/{project_id}/issues/{issue['id']}",
        json={"status": "Done"},
        headers=headers,
    )
    _cleanup_overrides()

    assert empty_update.status_code == 422
    assert empty_update.json()["error"]["code"] == "validation_error"
    assert valid_update.status_code == 200
    events = list(audit_events._items.values())
    assert any(event["event_type"] == "issue.updated" for event in events)
