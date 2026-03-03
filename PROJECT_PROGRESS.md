# Yumigura Project Progress

## Project Identity
- Project name: `Yumigura`
- Goal: Build a Jira-like ticketing system with MongoDB and optional MCP server capabilities.
- Cost constraint: Free/local-first setup (no paid cloud dependencies).

## Repository and Location
- Active working repo: `/Users/shivamsinghrawat/Desktop/Yume_Rei/Yumigura`
- Git repo is initialized in this folder and connected to `origin/main`.

## What Has Been Completed (Phase 0)
- Created FastAPI starter backend scaffold.
- Added MongoDB async connection layer (`motor`).
- Added base API routes:
  - `/` root endpoint
  - `/api/v1/health` health endpoint
- Added test setup with starter tests for root and health endpoints.
- Added lint/test configuration (`ruff`, `pytest`).
- Added Docker support:
  - `Dockerfile`
  - `docker-compose.yml` (API + MongoDB)
- Added local developer utilities:
  - `Makefile` (`setup`, `run`, `test`, `lint`, `up`, `down`)
  - `.env.example`
  - `.gitignore`

## Naming Cleanup Completed
All primary naming has been aligned to Yumigura conventions:
- App name: `Yumigura`
- Mongo DB name: `yumigura`
- Compose container names:
  - `yumigura_api`
  - `yumigura_mongo`

## Current Runtime Status
- Docker compose build/start was successfully executed.
- Containers confirmed running:
  - `yumigura_api` on port `8000`
  - `yumigura_mongo` on port `27017`

## Current Project Structure
- `app/main.py` - FastAPI app and lifecycle
- `app/core/config.py` - settings/env configuration
- `app/db/mongo.py` - Mongo client setup
- `app/api/health.py` - health route
- `tests/test_health.py` - starter tests
- `docker-compose.yml` - local app + db services
- `Dockerfile` - API image build
- `README.md` - setup and run docs

## Agreed Development Phases

### Phase 0: Foundation (Completed)
- Repo initialization and base scaffold
- FastAPI + MongoDB + Docker Compose setup
- Basic lint/test configuration

### Phase 1: Core Ticketing
- Authentication (JWT)
- User model and organization/project setup
- Issue CRUD (`Bug`, `Task`, `Story`)
- Comments, labels, priority, assignee
- Basic RBAC (owner/admin/member)

### Phase 2: Jira-like Workflow
- Custom statuses and transitions
- Kanban board, backlog, sprint model
- Activity log and issue history

### Phase 3: Power Features
- Search and filtering improvements
- Attachments using local filesystem (free storage)
- Notifications (in-app first, optional email)

### Phase 4: MCP Server Mode + Hardening
- Expose ticket operations as MCP tools:
  - `create_issue`
  - `update_issue`
  - `search_issues`
  - `transition_issue`
  - `add_comment`
- Permission checks and audit logging for MCP actions
- Docs, tests, backup scripts, production hardening

## Free-Only Infrastructure Decisions
- Backend: FastAPI (open-source)
- Database: MongoDB Community (local)
- File storage: local disk (`./data/uploads`)
- Optional cache/queue: local Redis (if needed later)
- Deployment path: self-hosted Docker

## Phase 1 Handoff Plan (Start Here)
1. Add auth module:
- JWT token issue/verify
- Password hashing
- Login/register endpoints

2. Define base data models/collections:
- `users`
- `organizations`
- `projects`
- `issues`
- `comments`

3. Implement issue APIs:
- Create issue
- Get issue by id/key
- List issues with filters
- Update issue
- Delete/soft-delete issue

4. Add RBAC guards:
- Organization/project level membership checks
- Role checks per endpoint

5. Add tests:
- Auth tests
- CRUD tests
- Permission tests

## Useful Run Commands
```bash
cd "/Users/shivamsinghrawat/Desktop/Yume_Rei/Yumigura"
cp .env.example .env
docker compose up --build
```

```bash
make test
make lint
```

## Notes
- `.env` is intentionally local and untracked.
- Keep all new work in this Desktop Yumigura repo only.
