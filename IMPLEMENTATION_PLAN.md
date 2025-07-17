# Monzo App: Implementation Plan

---

## 1. Project Setup

- Initialize repo:
  - Create a new directory and initialize a git repo.
  - Set up a Python virtual environment.
- Tooling:
  - Add `black`, `isort`, `flake8`, `mypy`, `pytest`, `responses` to `requirements.txt`.
  - Add `.editorconfig` and pre-commit hooks for formatting/linting.
- Directory structure:
  ```
  monzo_app/
    app/
      __init__.py
      models.py
      db.py
      monzo/
        __init__.py
        client.py
        sync.py
      business/
        __init__.py
        autosorter.py
        analytics.py
      api/
        __init__.py
        routes.py
      ui/
        __init__.py
        dashboard.py
      jobs/
        __init__.py
        scheduler.py
      config.py
    tests/
    requirements.txt
    README.md
    .env.example
  ```

---

## 2. Database Design & Setup

- Choose DB:
  - Prefer PostgreSQL for production, SQLite for dev/testing.
- Models:
  - `Account`: id, name, type, closed, etc.
  - `Pot`: id, account_id, name, pot_current_id, etc.
  - `Transaction`: id, account_id, pot_current_id, created, amount, description, category, metadata (JSON), etc.
  - `SyncMeta`: id, account_id, last_synced_at, etc.
- Migrations:
  - Use Alembic for schema migrations.
- Session management:
  - Use SQLAlchemy sessionmaker, context managers.

---

## 3. Monzo API Client

- OAuth2 flow:
  - Implement login, token refresh, logout.
- API wrappers:
  - `get_accounts()`, `get_pots()`, `get_transactions(account_id, since, before, batch_size)`, etc.
- Error handling:
  - Handle rate limits, token expiry, network errors robustly.

---

## 4. Sync Logic

- Startup sync:
  - On first run, fetch all accounts, pots, and transactions (batching as needed).
- Incremental sync:
  - On schedule or manual trigger, fetch only new transactions since last sync.
- Batching:
  - Fetch and insert transactions in batches (e.g., 200–500 at a time).
- Concurrency:
  - Serialize sync jobs (one at a time).
- Error handling:
  - Rollback on DB errors, log and continue on bad data.

---

## 5. Business Logic Layer

- Autosorter:
  - Use DB as source of truth.
  - Bills pot logic: always use `pot_current_id` for calculations.
- Analytics:
  - Use DB queries for all calculations.
- Configurable exclusions:
  - Allow user to exclude accounts/pots via config or UI.

---

## 6. API & UI

- REST API:
  - Endpoints for manual sync, status, business logic triggers.
- UI:
  - Dashboard for sync status, manual triggers, error reporting.
  - Login/logout with clear feedback.
  - Show last sync time, errors, and data freshness.

---

## 7. Background Jobs

- Scheduler:
  - Use APScheduler or Celery for scheduled syncs (every 6 hours).
  - Manual sync trigger via API/UI.
- Job control:
  - Prevent overlapping syncs.

---

## 8. Testing & Observability

- Unit tests:
  - For all sync, business logic, and API endpoints.
- Integration tests:
  - Mock Monzo API with `responses`.
- Logging:
  - Structured logs for sync jobs, errors, and business logic.
- Monitoring:
  - Health endpoints, error alerting (email/Slack).

---

## 9. Deployment & Operations

- Containerization:
  - Dockerfile for reproducible builds.
- Config:
  - Use `.env` for secrets/config.
- Documentation:
  - README with setup, usage, troubleshooting.
  - API docs (Swagger/OpenAPI if using FastAPI).

---

## 10. Polish & Launch

- User feedback:
  - Add clear error messages and status indicators.
- Performance tuning:
  - Profile sync, optimize queries, tune batch sizes.
- Security:
  - Secure secrets, validate all inputs, use HTTPS in production.

---

# Milestone Breakdown

1. Project scaffolding, tooling, and DB models
2. Monzo API client and OAuth2
3. Sync logic (startup + incremental)
4. Business logic (autosorter, analytics)
5. API and UI
6. Background jobs and scheduling
7. Testing and logging
8. Deployment, docs, and polish 