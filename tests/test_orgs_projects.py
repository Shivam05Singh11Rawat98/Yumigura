from fastapi.testclient import TestClient

from app.api.deps import (
    get_audit_collection,
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

    async def update_one(self, query: dict, update: dict) -> None:
        item = await self.find_one(query)
        if item is None:
            return
        for key, value in update.get("$set", {}).items():
            item[key] = value

    def find(self, query: dict) -> FakeCursor:
        docs = [
            item
            for item in self._items.values()
            if all(item.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(docs)


def _make_client() -> tuple[
    TestClient,
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
    audit_events = FakeCollection()

    app.dependency_overrides[get_user_collection] = lambda: users
    app.dependency_overrides[get_organization_collection] = lambda: organizations
    app.dependency_overrides[get_organization_member_collection] = lambda: organization_members
    app.dependency_overrides[get_project_collection] = lambda: projects
    app.dependency_overrides[get_project_member_collection] = lambda: project_members
    app.dependency_overrides[get_audit_collection] = lambda: audit_events
    return (
        TestClient(app),
        users,
        organizations,
        organization_members,
        projects,
        project_members,
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


def test_create_and_list_organizations() -> None:
    client, _, _, _, _, _, _ = _make_client()
    headers = _auth_headers(client, "owner@example.com")

    create = client.post(
        "/api/v1/organizations",
        json={"name": "Yumigura Org", "slug": "yumigura-org"},
        headers=headers,
    )
    assert create.status_code == 201
    org = create.json()
    assert org["slug"] == "yumigura-org"

    listing = client.get("/api/v1/organizations", headers=headers)
    _cleanup_overrides()

    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["name"] == "Yumigura Org"


def test_org_admin_can_create_project() -> None:
    client, _, _, _, _, _, _ = _make_client()
    owner_headers = _auth_headers(client, "owner2@example.com")
    admin_headers = _auth_headers(client, "admin2@example.com")

    create_org = client.post(
        "/api/v1/organizations",
        json={"name": "Project Org", "slug": "project-org"},
        headers=owner_headers,
    )
    org_id = create_org.json()["id"]

    owner_me = client.get("/api/v1/auth/me", headers=owner_headers).json()
    admin_me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    add_admin = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": admin_me["id"], "role": "admin"},
        headers=owner_headers,
    )
    assert add_admin.status_code == 201
    assert owner_me["id"] != admin_me["id"]

    create_project = client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"key": "YUM", "name": "Main Project", "description": "Core project"},
        headers=admin_headers,
    )
    _cleanup_overrides()

    assert create_project.status_code == 201
    assert create_project.json()["key"] == "YUM"


def test_org_endpoints_require_auth() -> None:
    client, _, _, _, _, _, _ = _make_client()
    response = client.get("/api/v1/organizations")
    _cleanup_overrides()

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Not authenticated"


def test_member_cannot_create_project() -> None:
    client, _, _, _, _, _, _ = _make_client()
    owner_headers = _auth_headers(client, "owner3@example.com")
    member_headers = _auth_headers(client, "member3@example.com")

    create_org = client.post(
        "/api/v1/organizations",
        json={"name": "Restricted Org", "slug": "restricted-org"},
        headers=owner_headers,
    )
    org_id = create_org.json()["id"]

    member_me = client.get("/api/v1/auth/me", headers=member_headers).json()
    add_member = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": member_me["id"], "role": "member"},
        headers=owner_headers,
    )
    assert add_member.status_code == 201

    forbidden = client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"key": "RST", "name": "Should Fail"},
        headers=member_headers,
    )
    _cleanup_overrides()

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["message"] == "Not allowed"


def test_org_list_supports_sort_and_pagination() -> None:
    client, _, _, _, _, _, _ = _make_client()
    headers = _auth_headers(client, "owner4@example.com")

    client.post(
        "/api/v1/organizations",
        json={"name": "Bravo Org", "slug": "bravo-org"},
        headers=headers,
    )
    client.post(
        "/api/v1/organizations",
        json={"name": "Alpha Org", "slug": "alpha-org"},
        headers=headers,
    )

    response = client.get(
        "/api/v1/organizations",
        params={"sort_by": "name", "sort_order": "asc", "limit": 1, "offset": 0},
        headers=headers,
    )
    _cleanup_overrides()

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "Alpha Org"


def test_member_updates_write_audit_events() -> None:
    client, _, _, _, _, _, audit_events = _make_client()
    owner_headers = _auth_headers(client, "owner5@example.com")
    admin_headers = _auth_headers(client, "admin5@example.com")

    org = client.post(
        "/api/v1/organizations",
        json={"name": "Audit Org", "slug": "audit-org"},
        headers=owner_headers,
    ).json()
    admin = client.get("/api/v1/auth/me", headers=admin_headers).json()

    add_member = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"user_id": admin["id"], "role": "admin"},
        headers=owner_headers,
    )
    _cleanup_overrides()

    assert add_member.status_code == 201
    events = list(audit_events._items.values())
    assert any(event["event_type"] == "organization_member.added" for event in events)
