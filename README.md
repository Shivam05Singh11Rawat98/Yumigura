# Yumigura (Phase 0)

Phase 0 starter template for a ticketing system using FastAPI + MongoDB with zero cloud cost.

## Stack
- FastAPI (Python API)
- MongoDB Community (local Docker)
- Motor (async Mongo driver)
- Ruff + Pytest

## Project Structure
- `app/main.py` - FastAPI app and lifecycle
- `app/core/config.py` - environment settings
- `app/db/mongo.py` - Mongo connection utilities
- `app/api/health.py` - health endpoint
- `tests/test_health.py` - starter tests
- `docker-compose.yml` - local API + Mongo services

## 1) Local Run (without Docker)

```bash
cp .env.example .env
make setup
make run
```

Open:
- API root: http://localhost:8000/
- Swagger docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

## 2) Docker Run (recommended)

```bash
cp .env.example .env
docker compose up --build
```

## Commands

```bash
make test
make lint
make down
```

## Next Phase (Phase 1)
- User/Auth model (JWT)
- Organizations/Projects
- Issue CRUD (`Bug`, `Task`, `Story`)
- Basic RBAC

### Phase 1 Progress (Started)
- Auth endpoints added:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `GET /api/v1/auth/me` (Bearer token)
- Organization/Project endpoints added:
  - `POST /api/v1/organizations`
  - `GET /api/v1/organizations`
  - `POST /api/v1/organizations/{organization_id}/members`
  - `GET /api/v1/organizations/{organization_id}/members`
  - `POST /api/v1/organizations/{organization_id}/projects`
  - `GET /api/v1/organizations/{organization_id}/projects`
  - `POST /api/v1/projects/{project_id}/members`
  - `GET /api/v1/projects/{project_id}/members`
- Issue/Comment endpoints added:
  - `POST /api/v1/projects/{project_id}/issues`
  - `GET /api/v1/projects/{project_id}/issues`
  - `GET /api/v1/projects/{project_id}/issues/{issue_id}`
  - `PATCH /api/v1/projects/{project_id}/issues/{issue_id}`
  - `DELETE /api/v1/projects/{project_id}/issues/{issue_id}` (soft delete)
  - `POST /api/v1/issues/{issue_id}/comments`
  - `GET /api/v1/issues/{issue_id}/comments`
- RBAC roles now enforced:
  - Organization roles: `owner`, `admin`, `member`
  - Project roles: `admin`, `member` (org owner is treated as highest privilege)
- Hardening completed:
  - Standardized API error contract: `{"error": {"code", "message", "details?"}}`
  - Pagination/sorting on list endpoints (`limit`, `offset`, `sort_by`, `sort_order`)
  - Audit events for issue and membership mutations (`audit_events` collection)
  - Stricter request validation (slug/key patterns, label constraints, non-empty issue updates)
- Security utilities added:
  - Password hashing (`passlib`)
  - JWT create/verify (`python-jose`)
- New env settings:
  - `JWT_SECRET_KEY`
  - `JWT_ALGORITHM`
  - `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`

## MCP Direction (Phase 4)
This project will expose ticket actions as MCP tools later:
- `create_issue`
- `update_issue`
- `search_issues`
- `transition_issue`
- `add_comment`

## Additional Docs
- `ARCHITECTURE.md` - architecture and data model diagrams
- `DEVELOPING.md` - local development workflow and troubleshooting
