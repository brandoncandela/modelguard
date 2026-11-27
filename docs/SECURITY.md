# Security

ModelGuard is a portfolio project that runs on synthetic data. This page describes the controls it implements and the gaps a production deployment would need to close.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository rather than a public issue.

## Authentication

- Users sign in with a username and password at `POST /api/v1/auth/login`. Passwords are hashed with bcrypt (cost 12).
- A successful sign-in returns a signed JWT (HS256) with the username, role, issuer and expiry (60 minutes by default, `MODELGUARD_ACCESS_TOKEN_MINUTES`). Every API call except health and login requires it.
- Five failed sign-ins lock the account for 15 minutes (configurable). Failed sign-ins, lockouts and successful sign-ins are written to the audit trail with the client IP.
- Demo users get the password in `MODELGUARD_DEMO_PASSWORD` when the database is seeded. If it is not set, the seed generates a random one and prints it once. No password is stored in the repository.

## Authorisation

- Four roles (administrator, model owner, validator, compliance reviewer) map to explicit permissions in `backend/app/core/permissions.py`. Each endpoint declares the permission it needs.
- Services enforce object-level rules on top of roles: owners edit only their own models and thresholds; validators must be independent of the model; approvers cannot have worked on the validation or own the model; remediation owners cannot close their own findings; assessors cannot review their own AI assessments; owners cannot approve their own AI systems.
- The frontend hides actions the user cannot take, but the server checks every request again.

## Input validation and errors

- Request bodies and query parameters are validated with Pydantic: patterns for IDs, enums for controlled values, length limits, date ordering, and threshold direction checks.
- Uploaded evidence is limited to 10 MB and to PDF, CSV, TXT, JSON, PNG, JPG, XLSX and DOCX. File names are sanitised, files are stored under their SHA-256 rather than the user's file name, and downloads re-check the hash.
- Errors return one JSON envelope with a code, message and request ID. Unexpected exceptions are logged with a stack trace and return a generic message.

## Configuration and secrets

- All configuration comes from environment variables (`MODELGUARD_*`) or a local `.env` file that git ignores. `.env.example` documents every setting without values.
- In production mode the API refuses to start without a secret key of at least 32 characters. In development it generates a random key for the process and logs a warning.
- Docker Compose takes the PostgreSQL password from `.env` and fails if it is missing.

## Audit trail

- Material changes and approvals (inventory changes, threshold changes, monitoring runs, breach handling, validation and finding transitions, evidence, AI assessments and decisions, evaluation runs, control changes and tests, report generation, sign-ins) are written to `audit_events` in the same transaction as the change.
- Each event stores the hash of the previous event and a SHA-256 of its own canonical content. `prev_hash` is unique so the chain cannot fork, and writes are serialised.
- Database triggers block UPDATE, DELETE and (on PostgreSQL) TRUNCATE on the audit table. An ORM guard blocks the same at the application layer.
- `GET /api/v1/audit/verify` recomputes the whole chain. A test bypasses the trigger on purpose and confirms verification catches the edit.

## HTTP

- Responses carry `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` and a restrictive Content-Security-Policy on API responses. The nginx container adds a CSP for the web app.
- CORS is limited to the origins in `MODELGUARD_CORS_ORIGINS`.
- Every request gets an `X-Request-ID` that appears in logs and audit events.

## Logging

The API logs one JSON line per request with method, path, status, duration and request ID. Passwords and tokens are never logged.

## Known gaps

- The access token is kept in browser session storage, which a cross-site scripting flaw could read. An HttpOnly, SameSite cookie with CSRF protection would be stronger.
- No single sign-on, multi-factor authentication or token revocation list. Tokens stay valid until they expire.
- Account lockout is the only brute-force control; there is no IP rate limiting.
- The audit write lock on SQLite is per process. Run the API with one worker on SQLite, or use PostgreSQL, where an advisory lock serialises writes across processes.
- Evidence and reports are stored on local disk. Production would use encrypted object storage with retention rules.
- Dependencies are pinned but not automatically scanned in CI.
