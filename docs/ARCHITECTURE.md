# Architecture

This document describes what was built. The plan written before coding is in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Components

```
frontend/   React 18 + TypeScript + Tailwind, built with Vite
  src/api         fetch client: bearer token, JSON or multipart, error envelope, authenticated downloads
  src/auth        sign-in, session, permission checks from /auth/me
  src/components  app shell, data table, badges, drawers, modals, Plotly wrapper (loaded on demand)
  src/pages       one page per navigation section (nine) plus login

backend/    FastAPI + SQLAlchemy 2.0 + Alembic
  app/api         routers per module, request validation with Pydantic, RBAC dependencies
  app/core        settings from the environment, JWT and bcrypt, permission matrix, JSON logging, errors
  app/models      ORM models for 38 tables
  app/services    workflow and permission rules: inventory, monitoring, simulation, validation,
                  AI governance, regulatory controls, reports, audit
  app/analytics   pure functions: classification metrics, PSI, drift tests, breach severity,
                  LLM evaluation, disparity testing
  app/simulation  the synthetic bank: customers, watch lists, monthly activity, data quality defects,
                  and the ten detection models that score it
  app/reporting   executive KPIs, trends, committee packs, PDF rendering
  app/seed        reference data and seeded governance history
  alembic         migrations, including database triggers that make the audit table append-only
```

## Request flow

1. The browser calls `/api/v1/...` with a bearer token. In development Vite proxies `/api` to the backend; in Docker nginx does.
2. A FastAPI dependency decodes the token, loads the user and checks the role permission for the endpoint.
3. The router validates the body with Pydantic and calls a service function.
4. The service applies the business rules (ownership, independence, workflow transitions, prerequisites), changes the records and appends an audit event in the same database transaction.
5. The router commits and returns JSON. Domain errors map to 400, 401, 403, 404, 409 or 422 with one error envelope and the request ID.

Every response carries `X-Request-ID`, and the same ID is written to the JSON log line and to any audit event the request creates.

## Monitoring data flow

```
seed / simulate  ->  transactions, applications, articles      (raw synthetic activity)
                 ->  data quality rules flag defects            (app/simulation/dq.py)
                 ->  ten models score every record              (app/simulation/detectors.py)
                 ->  scored_records + alerts with dispositions
monitoring run   ->  load the period's scored records and the reference window
                 ->  metrics, PSI, input drift tests            (app/analytics)
                 ->  compare with the model's thresholds        -> metric_results, breaches
                 ->  supersede earlier open breaches for the same metric
dashboard        ->  KPIs and trends are queries over these tables; nothing is typed in
```

The seed generates twelve months (November 2025 to October 2026 by default) and runs monitoring for every month. The drift simulator generates the next month with a chosen drift level, loads it, and runs monitoring on it, so new breaches appear in the app within a few seconds.

## Design decisions

**Analytics are pure functions.** `app/analytics` has no database or framework imports. Each function is tested against values worked out by hand (for example a two-bin PSI and a confusion matrix). Services do the I/O.

**Rules live in services, not in the UI.** The frontend hides buttons the user cannot use, but the server enforces every rule again. For example, a validator who owns a model cannot be assigned to validate it, an approver cannot have worked on the validation, and a finding cannot close without remediation evidence and an independent validator.

**The synthetic bank is deterministic.** Every random draw comes from a generator keyed on the seed, the purpose and the period, so any month can be regenerated on its own and the same seed and anchor date always give the same data. The machine learning models are retrained from the reference window when needed instead of being stored as pickled objects.

**Detection models are real code.** Transaction monitoring is a weighted rules engine. Suspicious activity detection is scikit-learn gradient boosting. Onboarding risk is logistic regression. Adverse media is TF-IDF with logistic regression. Screening uses character n-gram TF-IDF cosine similarity. The exceptions are the two LLM-based systems: triage recommendations are simulated from seeded probabilities, and the research assistant is evaluated on recorded responses.

**The audit trail is tamper-evident.** Each event stores the SHA-256 of the previous event's hash plus its own canonical content. `prev_hash` is unique, writes are serialised (advisory lock on PostgreSQL, process lock on SQLite), and triggers block UPDATE, DELETE and TRUNCATE. `GET /audit/verify` recomputes the chain.

**Seeded history is not presented as live activity.** Validation and finding histories carry their historical dates in `workflow_events`. The audit trail records one event saying the history was imported, rather than inventing backdated audit events.

**Files are stored by hash.** Evidence and generated reports are stored on disk under their SHA-256. Downloads re-hash the file and refuse to serve it if the content no longer matches.

## Database

38 tables. The main groups:

| Group | Tables |
|---|---|
| People and inventory | `users`, `models`, `model_thresholds` |
| Synthetic activity | `customers`, `transactions`, `applications`, `media_articles`, `watchlist_entries`, `alerts`, `scored_records`, `simulation_periods`, `system_settings` |
| Monitoring | `monitoring_runs`, `metric_results`, `feature_drift`, `breaches` |
| Validation | `validations`, `validation_approvals`, `findings`, `evidence`, `workflow_events` |
| AI governance | `ai_systems`, `assessment_templates`, `assessment_questions`, `ai_assessments`, `assessment_responses`, `llm_eval_cases`, `llm_recorded_responses`, `llm_eval_runs`, `llm_eval_results`, `bias_test_results` |
| Regulatory | `regulatory_sources`, `regulatory_requirements`, `controls`, `control_requirements`, `control_models`, `control_test_results` |
| Audit and reports | `audit_events`, `reports` |

Column definitions are in [DATA_DICTIONARY.md](DATA_DICTIONARY.md). Migrations live in `backend/alembic/versions`: `0001` creates the schema and `0002` adds the audit triggers for PostgreSQL and SQLite.

## Configuration

All settings come from environment variables with the `MODELGUARD_` prefix, optionally from a `.env` file that git ignores. Nothing secret has a default. In production the API refuses to start without a secret key of at least 32 characters. See [.env.example](../.env.example).

## Deployment

`docker-compose.yml` runs three containers:

| Service | Image | Purpose |
|---|---|---|
| `db` | postgres:16-alpine | Database with a named volume |
| `api` | built from `backend/Dockerfile` (python:3.12-slim, non-root user) | Waits for the database, applies migrations, seeds on first start, serves uvicorn on 8000 |
| `web` | built from `frontend/Dockerfile` (Node build, nginx:1.27-alpine) | Serves the built app on 8080 and proxies `/api` to the API, with security headers |

## What was verified, and where

| Check | Where it ran |
|---|---|
| 75 backend tests on SQLite | Development machine (Python 3.9.6) |
| Same suite on PostgreSQL 16.2 | Development machine, using the `pgserver` package to run a local PostgreSQL |
| Frontend typecheck and production build | Development machine (Node 26) |
| Every page, in the browser | Development machine, against the seeded database |
| Every page at phone width (390 px): no sideways page scroll, wide tables scroll inside their panel | Development machine, headless Chrome |
| Docker image builds and Compose start-up | GitHub Actions only. Docker is not installed on the development machine. |
| Python 3.12 test run | GitHub Actions |
