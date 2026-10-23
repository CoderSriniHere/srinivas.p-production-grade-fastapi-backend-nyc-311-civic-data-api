# NYC 311 Civic Data API

A production-grade FastAPI reference project: a multi-tenant API over NYC's public 311 service-request dataset. Each city agency (NYPD, HPD, DSNY, ...) is a tenant that can only see its own complaints. Built to exercise real backend concerns end to end — auth, caching, rate limiting, background jobs, real-time streaming, and observability — not just CRUD.

## Stack

- **API**: FastAPI (async), Uvicorn
- **Database**: PostgreSQL via SQLAlchemy 2.0 (async) + Alembic migrations
- **Cache / queue**: Redis — response caching, sliding-window rate limiting, ARQ job queue
- **Background jobs**: ARQ worker (separate process) for report generation
- **Real-time**: WebSocket (`/ws/live`) for a pushed live dashboard, SSE for job-progress streaming
- **Auth**: JWT bearer tokens and API keys, role-based scopes
- **Observability**: structlog (JSON logs with request IDs), Prometheus metrics, liveness/readiness health checks
- **Containerization**: Docker Compose (Postgres, Redis, app, worker, Prometheus)

## Prerequisites

- Docker and Docker Compose
- Python 3.12 (only needed if running the app outside Docker, or running the ETL/seed scripts locally)

## Quickstart

1. Copy the environment template and adjust if needed:

   ```
   cp .env.example .env
   ```

2. Start everything:

   ```
   docker-compose up --build
   ```

   This brings up Postgres, Redis, the API (runs `alembic upgrade head` on boot), the ARQ worker, and Prometheus. The API is available at `http://localhost:8001`.

3. Seed one demo login per agency:

   ```
   python -m app.etl.seed_users
   ```

   Prints the shared demo password and one `{agency}@nyc311.gov` login per seeded agency (e.g. `nypd@nyc311.gov`, role `admin`).

4. Load real complaint data from NYC Open Data:

   ```
   python -m app.etl.load_complaints --rows 50000
   ```

   Pulls from the Socrata Open Data API (dataset `erm2-nwe9`) and upserts into Postgres. Safe to re-run — existing rows are skipped via `unique_key`. Requests are currently unauthenticated against Socrata's public tier; for a large pull (the default is 500,000 rows) consider adding a free Socrata app token to avoid throttling.

## Auth

Two ways to authenticate:

- **JWT** — `POST /auth/register` or `POST /auth/login` returns a bearer token. Scopes are derived from role (`staff` → read, `analyst` → read + export, `admin` → read + write + export + admin).
- **API key** — `POST /auth/api-keys` (admin only) issues a key shown once; send it via `X-API-Key`. Scopes are set independently at creation time.

Every complaint-related query is scoped to the caller's `agency_code` — one tenant cannot see another's data.

## Key endpoints

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `PATCH /auth/users/{id}/role`, `POST/GET/DELETE /auth/api-keys` |
| Complaints | `GET/POST /complaints`, `GET/PATCH /complaints/{id}`, `GET /complaints/export` (streamed CSV) |
| Attachments | `POST/GET /complaints/{id}/attachments`, `GET .../attachment/{id}/download` |
| Reports | `POST /reports` (enqueue), `GET /reports/{id}`, `GET /reports/{id}/result`, `GET /reports/{id}/stream` (SSE) |
| Live | `WS /ws/live` |
| Ops | `GET /health/live`, `GET /health/ready`, `GET /metrics` (admin scope) |

## Migrations

```
alembic upgrade head        # apply
alembic revision --autogenerate -m "..."   # generate a new one after model changes
```

## Running without Docker

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Requires a local Postgres and Redis reachable at the URLs in `.env` (see `docker-compose.yml` for matching ports if you'd rather run just the datastores in Docker and the app natively).
