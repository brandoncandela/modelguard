# ModelGuard implementation plan

This is the plan written before any code, kept in the repo so the build can be checked against it. ARCHITECTURE.md describes what was actually built.

## Starting point

- New repo `repos/modelguard`, alongside the other portfolio projects. Publishing target `github.com/brandoncandela/modelguard`.
- Local machine: Python 3.9, Node 26. No PostgreSQL server and no Docker. The `pgserver` wheel ships PostgreSQL binaries, so the test suite can still run against a real PostgreSQL. Docker Compose files are written for users who have Docker and are checked in CI.
- The simulated institution is Candela Bank, a fictional international bank (US, UK, EU, Singapore, UAE). Every record is generated from fixed seeds.

## 1. Architecture

```
React + TypeScript + Tailwind (Vite)          Plotly.js charts
        |  JSON over HTTPS, JWT bearer token
FastAPI application (/api/v1, OpenAPI at /docs)
  api/          routers per module, request validation (Pydantic)
  core/         settings from environment, security (JWT, bcrypt), RBAC, logging, errors
  services/     workflow rules: inventory, validation, findings, AI governance, controls, reports
  analytics/    pure functions: confusion metrics, PSI/CSI, KS and chi-square drift, breach severity, LLM evaluator
  synthetic/    seeded generators for customers, transactions, alerts, model scores, governance records
  reporting/    executive KPIs, committee packs, PDF rendering (ReportLab)
  db/           SQLAlchemy 2.0 models, sessions; Alembic migrations
        |
PostgreSQL 16 (Docker Compose)  or  SQLite file (local fallback, same migrations)
```

Design rules:

- Analytics are pure functions over pandas/NumPy arrays and are unit tested on hand-computed cases. Services load data, call analytics, and persist results. No metric value is written by hand anywhere.
- Every state change goes through a service function that checks role, ownership and workflow rules, then writes an append-only audit event in the same transaction.
- Audit events are hash chained (each event stores the SHA-256 of the previous event plus its own content). UPDATE and DELETE on the audit table are blocked by database triggers on both PostgreSQL and SQLite.

## 2. Database schema

| Table | Purpose | Key columns |
|---|---|---|
| users | staff directory and login | username, full_name, role (admin, model_owner, validator, compliance_reviewer), business_unit, password_hash, failed_logins, locked_until |
| models | Module A inventory | model_id (MDL-TM-001), name, business_owner_id, model_risk_owner_id, business_unit, category, methodology, methodology_type, geographies, risk_rating, lifecycle_stage, last/next_validation_date, approval_status, documentation_checklist, documentation_status, limitations, monitoring_frequency, is_archived |
| model_thresholds | KPI/KRI limits per model | model_id, metric, direction, warning_limit, breach_limit, rationale |
| customers | 1,000+ synthetic profiles | segment, country, nationality_region, industry, pep_flag, risk_score, risk_rating, latent typology label |
| transactions | 50,000+ synthetic transactions | customer, date, period, amount_usd, channel, direction, counterparty country, typology label, data quality issue |
| alerts | 5,000+ alerts across alerting models | model, customer, transaction, score, rule, disposition, escalated, sar_filed, productive |
| scored_records | every record each model scored, per period | model, period, record_ref, score, predicted, actual, disposition, segment, dq_issue |
| monitoring_runs | monitoring history | model, period, reference window, record count, triggered_by, scenario |
| metric_results | one row per metric per run | metric, value, numerator, denominator, details (JSON), status |
| feature_drift | input drift per feature per run | feature, PSI, KS statistic and p-value, chi-square p-value, drift flag |
| breaches | threshold breaches | metric, value, limits, severity, consecutive periods, status |
| validations | Module C | validation_id, model, type, scope, status, lead validator, independence attestation, schedule, outcome |
| validation_approvals | approval records | approver, decision, conditions, timestamp |
| findings | Module C findings | finding_id, validation, model, severity, category, status, management response, remediation owner, target dates, extensions |
| evidence | files and references for validations, findings, controls | owner entity, title, type, file name, SHA-256, size, uploaded_by |
| workflow_events | status history for validations, findings, assessments | entity, from, to, actor, comment |
| ai_systems | Module D inventory | system_id, linked model, use case, justification, owners, data sources, intended and prohibited use, oversight, explainability, bias testing, limitations, classification, approval status |
| assessment_templates, assessment_questions | configurable EU AI Act readiness template | category, code, question, article reference, weight, classification trigger |
| ai_assessments, assessment_responses | completed assessments | answers, evidence notes, category scores, derived classification, reviewer decision |
| llm_eval_cases, llm_recorded_responses, llm_eval_runs, llm_eval_results | deterministic LLM test suite | prompts, context, expected facts, recorded outputs per model version, scored results |
| regulatory_sources, regulatory_requirements | Module F sources | source type (regulation, supervisory guidance, internal policy), citation, URL, review date |
| controls, control_requirements, control_models, control_test_results | control library and mappings | owner, evidence requirement, status, gaps, remediation, automated test result |
| audit_events | append-only audit trail | actor, role, action, entity, changes, request id, prev_hash, hash |
| reports | generated PDF history | type, as-of date, generated_by, SHA-256 |

## 3. API (all under /api/v1, JSON, bearer token)

- Auth: `POST /auth/login`, `GET /auth/me` (includes the caller's permission list)
- Inventory: `GET /models` (search, filter, sort, paginate), `POST /models`, `GET/PATCH /models/{id}`, `POST /models/{id}/archive`, `POST /models/{id}/restore`, `GET /models/facets`, `GET /models/{id}/history`
- Monitoring: `GET /monitoring/summary`, `GET /monitoring/models/{id}/series`, `GET /monitoring/models/{id}/runs`, `GET /monitoring/runs/{run_id}`, `GET /monitoring/models/{id}/distribution`, `GET/PUT /monitoring/models/{id}/thresholds`, `PUT /monitoring/models/{id}/frequency`, `POST /monitoring/runs`, `GET /monitoring/breaches`, `POST /monitoring/breaches/{id}/acknowledge`, `POST /monitoring/simulate`, `GET /monitoring/methodology`
- Validations: `GET/POST /validations`, `GET/PATCH /validations/{id}`, `POST /validations/{id}/transition`, `POST /validations/{id}/evidence`, `GET /evidence/{id}/download`, `GET /validations/{id}/report.pdf`
- Findings: `GET/POST /findings`, `GET /findings/{id}`, `POST /findings/{id}/response`, `POST /findings/{id}/transition`, `POST /findings/{id}/extend`, `POST /findings/{id}/evidence`
- AI governance: `GET/POST /ai/systems`, `GET/PATCH /ai/systems/{id}`, `GET /ai/templates/active`, `POST /ai/templates/questions`, `POST /ai/systems/{id}/assessments`, `GET /ai/assessments/{id}`, `PUT /ai/assessments/{id}/responses`, `POST /ai/assessments/{id}/submit`, `POST /ai/assessments/{id}/review`, `GET /ai/eval/cases`, `POST /ai/eval/runs`, `GET /ai/eval/runs`, `GET /ai/eval/runs/{id}`, `POST /ai/systems/{id}/bias-test`
- Regulatory: `GET /regulatory/sources`, `GET /regulatory/requirements`, `GET /regulatory/controls`, `GET/PATCH /regulatory/controls/{id}`, `POST /regulatory/controls/test`, `GET /regulatory/coverage`
- Reporting: `GET /dashboard/executive`, `GET /dashboard/trends`, `GET /committees/{mrmc|fcmoc|aigc}`, `POST /reports`, `GET /reports`, `GET /reports/{id}/download`
- Audit: `GET /audit/events`, `GET /audit/verify`
- `GET /health`

Errors use one envelope: `{"error": {"code", "message", "details", "request_id"}}`.

## 4. Frontend structure

```
src/
  api/          fetch client with token and error envelope, typed endpoints
  auth/         login, session context, permission checks mirrored from /auth/me
  components/
    layout/     AppShell, Sidebar (nine sections), TopBar
    ui/         DataTable, KpiTile, StatusBadge, SeverityBadge, Panel, Tabs, Drawer, Modal, Field, Button, EmptyState, ErrorBanner
    charts/     PlotlyChart wrapper and chart builders
  pages/        ExecutiveOverview, ModelInventory, PerformanceMonitoring, ValidationManagement,
                FindingsRemediation, AIGovernance, RegulatoryControls, CommitteeReporting, AuditTrail, Login
  theme/        design tokens as CSS variables
```

## 5. Milestones

1. Backend architecture, database, migrations, synthetic data generator, seed command
2. Model inventory API and UI with CRUD, search, filter, archive, audit
3. Monitoring engine: metrics, PSI, drift tests, thresholds, breach severity, history, drift scenario
4. Validation workflow, findings lifecycle, evidence, overdue tracking
5. AI governance, EU AI Act readiness workflow, LLM evaluation suite, bias testing, regulatory control mapping
6. Executive dashboard, committee views, PDF reports
7. Security hardening, full test suite, PostgreSQL check, Docker, documentation, screenshots

Each milestone ends with the app running, its tests passing and a local commit.
