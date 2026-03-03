from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_user_collection
from app.main import app


class FakeInsertResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeUserCollection:
    def __init__(self) -> None:
        self._items: dict[str, dict] = {}

    async def find_one(self, query: dict) -> dict | None:
        if "_id" in query:
            return self._items.get(query["_id"])
        if "email" in query:
            for user in self._items.values():
                if user["email"] == query["email"]:
                    return user
        return None

    async def insert_one(self, document: dict) -> FakeInsertResult:
        inserted_id = str(len(self._items) + 1)
        self._items[inserted_id] = {"_id": inserted_id, **document}
        return FakeInsertResult(inserted_id)


def _make_client() -> tuple[TestClient, FakeUserCollection]:
    collection = FakeUserCollection()
    app.dependency_overrides[get_user_collection] = lambda: collection
    return TestClient(app), collection


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


def test_register_user_success() -> None:
    client, _ = _make_client()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "StrongPass123",
            "full_name": "Test User",
        },
    )
    _cleanup_overrides()

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["role"] == "member"


def test_register_duplicate_email_returns_conflict() -> None:
    client, collection = _make_client()
    existing_id = "existing"
    collection._items[existing_id] = {
        "_id": existing_id,
        "email": "dupe@example.com",
        "password_hash": "x",
        "full_name": None,
        "role": "member",
        "created_at": datetime.now(timezone.utc),
    }
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": "StrongPass123"},
    )
    _cleanup_overrides()

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_login_and_me_flow() -> None:
    client, _ = _make_client()
    register = client.post(
        "/api/v1/auth/register",
        json={"email": "flow@example.com", "password": "StrongPass123"},
    )
    token = register.json()["access_token"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    _cleanup_overrides()

    assert me.status_code == 200
    me_data = me.json()
    assert me_data["email"] == "flow@example.com"
    assert me_data["role"] == "member"


def test_login_invalid_credentials() -> None:
    client, _ = _make_client()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "StrongPass123"},
    )
    _cleanup_overrides()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_me_requires_auth() -> None:
    client, _ = _make_client()
    response = client.get("/api/v1/auth/me")
    _cleanup_overrides()

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
