# ModelGuard

**Financial crime model risk management and AI governance for a fictional international bank.**

![ModelGuard executive overview](docs/social-preview.jpg)

ModelGuard is a working application, not a mockup. It keeps a bank's inventory of financial crime models, measures how each model performs every month from the records it actually scored, runs independent validations and tracks findings to closure, assesses AI systems against the EU AI Act, maps internal controls to regulation, and produces committee reports as PDFs. Every change is written to a tamper-evident audit trail.

The bank (Candela Bank) and all of its data are fictional and generated from fixed seeds. Assessments and control tests in this app are internal governance tools. They are not certifications and do not establish compliance with any regulation.

## The business problem

A bank running transaction monitoring, sanctions screening, customer risk rating and newer machine learning and LLM tools has to show its supervisors that each model is inventoried, independently validated, monitored against agreed limits, and fixed when it fails. In practice that evidence lives in spreadsheets, email and slide decks, and the numbers in committee packs are typed in by hand. The questions a Head of Model Risk Management gets asked are simple to state and hard to answer quickly:

- Which models are overdue for validation, and which are breaching their performance limits right now?
- Did recall fall because the model got worse, because the population changed, or because the input data broke?
- Which findings are past their target date, who owns them, and who verified the fix?
- Which AI systems are in use, how are they classified under the EU AI Act, and has anyone tested the LLMs for fabricated answers?
- Can we prove nobody edited the approval history?

ModelGuard answers those from one database, with every figure traceable to the records behind it.

## What it does

| Module | What works |
|---|---|
| A. Model inventory | 10 financial crime models with owners, methodology, risk rating, lifecycle, validation dates, approval and documentation status, limitations, and each entry's classification under the April 2026 interagency guidance. Search, filter, sort, register, edit, archive and restore, with ownership rules and full change history. |
| B. Performance monitoring | Precision, recall, F1, false-positive rate, alert conversion, override rate, score PSI, input drift (PSI with Kolmogorov-Smirnov or chi-square tests) and data quality exceptions, computed monthly from 181,000 scored records. Configurable KPI and KRI limits per model, breach severity with escalation, acknowledgement, run history, and an in-app drift simulator. |
| C. Validation and findings | Validations move through Not Started, Scheduled, In Progress, Pending Review, then Approved, Conditionally Approved or Rejected. Independence is enforced for validators and approvers. Findings run from management response to remediation evidence to closure by an independent validator, with extensions, risk acceptance rules, overdue aging and SHA-256 hashed evidence. |
| D. AI governance | AI system inventory, a configurable EU AI Act readiness assessment across seven categories with classification triggers, committee approval rules, a deterministic LLM evaluation suite, and outcome disparity testing. |
| E. Executive reporting | Executive dashboard with the nine required KPIs and historical trends, separate packs for three committees, and downloadable PDF reports with stored hashes. |
| F. Regulatory governance and audit | Source library (regulation, supervisory guidance, internal policy) with review dates and supersession, 40 requirements, 21 controls mapped to requirements and models, 15 automated control tests over live data, and an append-only, hash-chained audit trail. |

## Architecture

```mermaid
flowchart LR
  UI["React + TypeScript + Tailwind<br/>Plotly charts"] -- "JSON over HTTPS<br/>bearer token" --> API
  subgraph API["FastAPI application"]
    R["Routers<br/>validation, RBAC"] --> S["Services<br/>workflow rules, audit"]
    S --> A["Analytics<br/>metrics, PSI, drift,<br/>severity, LLM eval, bias"]
    S --> P["Reporting<br/>committee packs, PDF"]
    SIM["Simulation<br/>synthetic bank, ten models"] --> S
  end
  S --> DB[("PostgreSQL 16<br/>or SQLite")]
  S --> FS[("Evidence and report files<br/>stored by SHA-256")]
```

Analytics are pure functions with no database access, so each one is unit tested against hand-computed values. Services load data, enforce workflow and permission rules, call the analytics and write an audit event in the same transaction. See [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology

| Layer | Tools |
|---|---|
| Frontend | React 18, TypeScript, Tailwind CSS, TanStack Query, Plotly.js |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic |
| Analytics and ML | pandas, NumPy, SciPy, scikit-learn (gradient boosting, logistic regression, TF-IDF) |
| Reports | ReportLab |
| Database | PostgreSQL 16 (Docker Compose), SQLite for local development |
| Testing | pytest (unit, integration, end to end), run on SQLite and PostgreSQL |
| Delivery | Docker, Docker Compose, GitHub Actions |

## Run it

### Option 1: local (Python 3.9 or newer, Node 20 or newer)

```bash
cp .env.example .env
```

Edit `.env` and set `MODELGUARD_SECRET_KEY` (generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`) and `MODELGUARD_DEMO_PASSWORD` (any value; every demo user signs in with it).

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m app.cli seed
.venv/bin/uvicorn app.main:app --port 8000
```

Seeding builds the database and generates twelve months of synthetic activity in about 11 seconds. In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The API documentation is at http://localhost:8000/docs.

### Option 2: Docker Compose with PostgreSQL

```bash
cp .env.example .env
```

Set `MODELGUARD_SECRET_KEY`, `MODELGUARD_DEMO_PASSWORD` and `POSTGRES_PASSWORD` in `.env`, then:

```bash
docker compose up --build
```

The app is served on http://localhost:8080. The API container waits for PostgreSQL, applies migrations and seeds on first start.

### Demo users

| Username | Role | Person |
|---|---|---|
| `admin` | Administrator | Avery Collins, Model Risk Technology |
| `jpatel` | Model owner | Jordan Patel, Transaction Monitoring Analytics |
| `nbrooks` | Validator | Nadia Brooks, Lead Model Validator |
| `hmarsh` | Compliance reviewer | Helen Marsh, Head of Model Risk Management |

Ten more synthetic staff (`skim`, `ewalsh`, `aduarte`, `bcarter`, `cmorgan`, `mreyes`, `tlindgren`, `gwu`, `dosei`, `lferreira`) use the same password. Try the drift simulator as `admin` on the Performance Monitoring page, approve a validation as `hmarsh`, and respond to a finding as `jpatel`.

## Screenshots

All screenshots are of the running application with seeded data.

| | |
|---|---|
| ![Executive overview](docs/screenshots/01-executive-overview.png) Executive overview | ![Model inventory](docs/screenshots/02-model-inventory.png) Model inventory |
| ![Model detail](docs/screenshots/03-model-detail.png) Model detail and SR 26-2 classification | ![Performance monitoring](docs/screenshots/04-performance-monitoring.png) Performance monitoring with limits |
| ![Drift analysis](docs/screenshots/05-drift-analysis.png) Score distribution and input drift tests | ![Validation workflow](docs/screenshots/06-validation-workflow.png) Validation awaiting approval |
| ![Findings](docs/screenshots/07-findings-remediation.png) Findings and remediation | ![EU AI Act assessment](docs/screenshots/08-eu-ai-act-assessment.png) EU AI Act readiness assessment |
| ![LLM evaluation](docs/screenshots/09-llm-evaluation.png) LLM evaluation with flagged responses | ![Regulatory controls](docs/screenshots/10-regulatory-controls.png) Regulatory coverage and controls |
| ![Committee reporting](docs/screenshots/11-committee-reporting.png) Committee reporting | ![Audit trail](docs/screenshots/12-audit-trail.png) Audit trail with chain verification |

## Sample outputs

From the seeded database (seed 20261031, data through October 2026, moderate drift over the last three months).

**Data generated:** 64,997 transactions, 8,139 alerts (3,024 escalated, 1,352 SARs), 1,200 customer risk profiles, 2,460 onboarding applications, 6,240 news articles, 180,974 scored records, 108 monitoring runs, 12 validations, 29 findings, 10 AI systems, 24 LLM test cases.

**Model performance, reference window (Nov 2025 to Apr 2026) against October 2026:**

| Model | Precision ref / Oct | Recall ref / Oct | What changed |
|---|---|---|---|
| MDL-TM-001 rules-based transaction monitoring | 21.1% / 20.8% | 59.4% / 49.0% | Structuring moved below the scenario band and pass-through moved to instant payments |
| MDL-SAD-007 gradient boosting detection | 71.0% / 63.0% | 99.6% / 81.7% | Same behaviour change, partly outside the training data; channel input PSI 0.156 |
| MDL-AM-006 adverse media classifier | 79.4% / 75.7% | 100% / 65.4% | New scam and money mule vocabulary unseen at training |
| MDL-SF-002 sanctions filtering | 9.3% / 8.4% | 84.5% / 82.4% | Data quality exceptions 5.5% after a payment platform migration dropped counterparty countries |

The ML model beats the rules on precision by roughly three times at the same point in time, and both degrade when launderers change behaviour. That is the pattern the monitoring module is built to catch.

**Control tests:** 9 of 15 automated tests pass. The six with exceptions point at real issues in the data: two models past their revalidation date, three findings past target, high-risk models with partial documentation, sanctions data quality over limit, an AI pilot running without an approved assessment, and an adverse media model in production with an expired approval.

**LLM evaluation:** the production research assistant (v1.2) fails with an 11.8% hallucination rate and 66.7% consistency; the candidate (v1.3-rc) passes. The investigation triage pilot (v0.9) fails policy compliance at 71.4% because it followed an instruction hidden in a customer letter and tipped off a customer. The evaluator catches all 17 defects planted across 10 responses and passes all 38 clean ones.

**PDF reports:** [executive committee report](docs/sample-reports/executive-committee-report.pdf), [MRMC pack](docs/sample-reports/mrmc-pack.pdf), [FCMOC pack](docs/sample-reports/fcmoc-pack.pdf), [AIGC pack](docs/sample-reports/aigc-pack.pdf), and validation reports for [transaction monitoring](docs/sample-reports/validation-report-transaction-monitoring.pdf), [customer risk rating](docs/sample-reports/validation-report-customer-risk-rating.pdf) and the [rejected AI triage pilot](docs/sample-reports/validation-report-ai-triage-rejected.pdf).

## API

OpenAPI documentation is served at `/docs` (Swagger UI) and `/redoc`. All endpoints are under `/api/v1`, take and return JSON, and require a bearer token from `POST /api/v1/auth/login`. Errors use one envelope: `{"error": {"code", "message", "details", "request_id"}}`.

| Area | Main endpoints |
|---|---|
| Auth | `POST /auth/login`, `GET /auth/me`, `GET /users` |
| Inventory | `GET/POST /models`, `GET/PATCH /models/{id}`, `POST /models/{id}/archive`, `POST /models/{id}/restore`, `GET /models/{id}/history`, `GET /models/facets` |
| Monitoring | `GET /monitoring/summary`, `GET /monitoring/models/{id}/series`, `GET /monitoring/runs/{run_id}`, `GET /monitoring/models/{id}/distribution`, `GET/PUT /monitoring/models/{id}/thresholds`, `POST /monitoring/runs`, `GET /monitoring/breaches`, `POST /monitoring/breaches/{id}/acknowledge`, `POST/DELETE /monitoring/simulate`, `GET /monitoring/methodology` |
| Validations | `GET/POST /validations`, `GET/PATCH /validations/{id}`, `POST /validations/{id}/transition`, `POST /validations/{id}/evidence`, `POST /validations/{id}/findings`, `POST /validations/{id}/report`, `GET /evidence/{id}/download` |
| Findings | `GET /findings`, `GET /findings/summary`, `GET /findings/{id}`, `POST /findings/{id}/response`, `POST /findings/{id}/transition`, `POST /findings/{id}/extend`, `POST /findings/{id}/evidence` |
| AI governance | `GET/POST /ai/systems`, `GET/PATCH /ai/systems/{id}`, `POST /ai/systems/{id}/decision`, `POST /ai/systems/{id}/assessments`, `GET /ai/assessments/{id}`, `PUT /ai/assessments/{id}/responses`, `POST /ai/assessments/{id}/submit`, `POST /ai/assessments/{id}/review`, `GET /ai/templates/active`, `POST /ai/templates/questions`, `POST /ai/eval/runs`, `GET /ai/eval/runs/{id}`, `POST /ai/systems/{id}/bias-test` |
| Regulatory | `GET /regulatory/sources`, `GET /regulatory/requirements`, `GET /regulatory/controls`, `GET/PATCH /regulatory/controls/{id}`, `POST /regulatory/controls/test`, `GET /regulatory/coverage` |
| Reporting | `GET /dashboard/executive`, `GET /dashboard/trends`, `GET /committees/{mrmc,fcmoc,aigc}`, `POST /reports`, `GET /reports`, `GET /reports/{id}/download` |
| Audit | `GET /audit/events`, `GET /audit/verify` |

## Metric definitions

| Metric | Formula | Notes |
|---|---|---|
| Precision | TP / (TP + FP) | Share of alerts that were truly suspicious or true list matches |
| Recall | TP / (TP + FN) | Uses synthetic ground truth for every record. Banks cannot see missed cases directly and estimate recall with below-the-line testing and look-backs. |
| F1 | 2PR / (P + R) | |
| False-positive rate | FP / (FP + TN) | The share of alerts that were false (FP / alerts) is reported alongside, since AML teams often call that the false positive rate |
| Alert conversion | Escalated alerts / alerts | From recorded investigator dispositions |
| Override rate | Decisions differing from the AI recommendation / decisions | AI triage only |
| PSI | sum((a - e) x ln(a / e)) | Bins at reference deciles, or by value for rules scores with 20 or fewer distinct values. Under 0.10 stable, 0.10 to 0.25 moderate, 0.25 or more significant. |
| Input drift | PSI plus KS (numeric) or chi-square (categorical) | Flagged only when significant at 1% with a material effect size, so large samples do not flag trivial shifts |
| Data quality exceptions | Records failing an input rule / records | Rules check amounts, currencies, counterparty countries, dates, missing fields |

Breach severity, threshold rules and validation rules are in [VALIDATION_METHODOLOGY.md](docs/VALIDATION_METHODOLOGY.md).

## Data dictionary

The schema has 38 tables. The main ones are `models`, `model_thresholds`, `customers`, `transactions`, `alerts`, `scored_records`, `monitoring_runs`, `metric_results`, `feature_drift`, `breaches`, `validations`, `findings`, `evidence`, `workflow_events`, `ai_systems`, `ai_assessments`, `llm_eval_runs`, `regulatory_sources`, `regulatory_requirements`, `controls` and `audit_events`. Column-level definitions and how the synthetic data is generated are in [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

75 tests cover inventory CRUD and permissions, metric, PSI and drift calculations against hand-computed values, threshold breaches and severity, the drift simulation, validation and finding workflows, AI assessment and evaluation, the evaluator catching every planted defect, disparity testing, regulatory mapping and control tests, PDF generation and content, audit chain tamper detection, and one end-to-end workflow from drift to committee report.

To run the same suite against PostgreSQL, point `MODELGUARD_TEST_DATABASE_URL` at an empty database:

```bash
MODELGUARD_TEST_DATABASE_URL=postgresql://user:password@localhost:5432/modelguard_test .venv/bin/python -m pytest -q
```

Locally the suite passes on SQLite and on PostgreSQL 16.2 (one SQLite-only tamper simulation is skipped there). GitHub Actions runs both, builds the frontend, and builds and starts the Docker Compose stack.

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md): components, data flow, design decisions, what was verified
- [MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md): inventory standards, roles, lifecycle and the ten models
- [VALIDATION_METHODOLOGY.md](docs/VALIDATION_METHODOLOGY.md): validation workflow, findings, monitoring metrics, thresholds, severity
- [AI_GOVERNANCE.md](docs/AI_GOVERNANCE.md): AI inventory, EU AI Act readiness assessment, LLM evaluation, bias testing
- [REGULATORY_MAPPING.md](docs/REGULATORY_MAPPING.md): sources, requirements, controls and coverage
- [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): tables, columns and synthetic data generation
- [SECURITY.md](docs/SECURITY.md): authentication, access control, audit trail and known gaps

## Known limitations

- All data is synthetic. Positive rates (suspicious activity, list matches) are higher than in production so monthly metrics have enough positives to be stable.
- Recall uses ground truth a real bank does not have.
- The AI triage assistant's recommendations are simulated from seeded probabilities, and the LLM suite scores recorded responses. No live model is called.
- The EU AI Act assessment is a readiness self-assessment built from the regulation's articles. It is not a conformity assessment or legal advice, and the dates it cites should be checked against the consolidated text.
- Requirement summaries are paraphrases. Read the sources before relying on them.
- Access tokens are kept in browser session storage, there is no single sign-on or MFA, and file storage is local disk. See [SECURITY.md](docs/SECURITY.md).
- The Docker images were not built on the development machine (no Docker installed); the CI workflow builds and starts them.

## Regulatory references

Sources were checked against the published text on 25 November 2026.

- Federal Reserve SR 26-2, OCC Bulletin 2026-13 and FDIC, *Supervisory Guidance on Model Risk Management* (17 April 2026), which supersedes SR 11-7 and SR 21-8 and rescinds OCC Bulletin 2011-12 and OCC Bulletin 2021-19
- Federal Reserve SR 11-7 and OCC Bulletin 2011-12, *Supervisory Guidance on Model Risk Management* (4 April 2011), kept as superseded references
- Federal Reserve SR 21-8 / OCC Bulletin 2021-19, *Interagency Statement on Model Risk Management for Bank Systems Supporting BSA/AML Compliance* (April 2021), superseded
- New York State Department of Financial Services, 3 NYCRR Part 504, *Transaction Monitoring and Filtering Program Requirements and Certifications*
- Regulation (EU) 2024/1689 (the EU AI Act), as amended by Regulation (EU) 2026/1744

Details and links are in [REGULATORY_MAPPING.md](docs/REGULATORY_MAPPING.md).

## About

Built by [Brandon Candela](https://brandoncandela.github.io), AML consultant (CAMS, CRISC, PMP) with six years of AML work at TD Bank, KPMG, IBM Promontory and Deutsche Bank. ModelGuard is the kind of tool model risk and financial crime teams need when every committee pack is assembled by hand.

MIT licensed. Built with AI coding tools.
