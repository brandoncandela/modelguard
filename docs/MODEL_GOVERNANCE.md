# Model governance

How Candela Bank (fictional) governs its financial crime models in ModelGuard. The policy names (MRM-POL-001, AI-POL-002, FCC-STD-003) are the fictional bank's internal policies. The supervisory sources they draw on are listed in [REGULATORY_MAPPING.md](REGULATORY_MAPPING.md).

## What goes in the inventory

Every model and model-like tool is inventoried, whatever its classification under the April 2026 interagency guidance (SR 26-2 / OCC Bulletin 2026-13). That guidance defines a model as a complex quantitative method that applies statistical, economic or financial theories, excludes deterministic rule-based processes, and places generative and agentic AI outside its scope. The bank records that classification on each entry, with a rationale, but applies the same lifecycle controls to all entries: transaction monitoring rules and screening engines are still validated under 3 NYCRR Part 504, and generative AI is still validated under AI-POL-002.

Each entry records: model ID, name, business owner, model risk owner, business unit, category, methodology and methodology type, vendor, version, geographies, risk rating and rationale, SR 26-2 classification and rationale, lifecycle stage, implementation date, last and next validation dates, approval status, documentation checklist and status, limitations, and monitoring frequency.

## The ten models

| ID | Name | Method | Risk | SR 26-2 classification | Business owner / model risk owner | Lifecycle | Approval |
|---|---|---|---|---|---|---|---|
| MDL-TM-001 | AML Transaction Monitoring Scenarios | Rules-based | High | Outside SR 26-2 definition (deterministic) | Marcus Reyes / Jordan Patel | Production | Conditionally Approved |
| MDL-SF-002 | Sanctions Payment Filtering | Fuzzy name matching | High | Outside SR 26-2 definition (deterministic) | Sofia Kim / Ethan Walsh | Production | Approved |
| MDL-NS-003 | Customer and Related-Party Name Screening | Fuzzy name matching | High | Outside SR 26-2 definition (deterministic) | Sofia Kim / Ethan Walsh | Production | Approved |
| MDL-CRS-004 | Customer Risk Rating Model | Statistical scoring | High | Model under SR 26-2 | Amira Duarte / Jordan Patel | Production | Conditionally Approved |
| MDL-PEP-005 | PEP Identification | Fuzzy name matching | Medium | Outside SR 26-2 definition (deterministic) | Sofia Kim / Ethan Walsh | Production | Approved |
| MDL-AM-006 | Adverse Media Relevance Classifier | NLP classification | Medium | Model under SR 26-2 | Amira Duarte / Ethan Walsh | Production | Approval Expired |
| MDL-SAD-007 | ML Suspicious Activity Detection | Machine learning | High | Model under SR 26-2 | Marcus Reyes / Jordan Patel | Production | Conditionally Approved |
| MDL-AII-008 | AI-Assisted AML Investigation Triage | Large language model | High | Outside SR 26-2 scope (generative AI) | Marcus Reyes / Ben Carter | Pre-Implementation Validation | Not Approved |
| MDL-LLM-009 | LLM Compliance Research Assistant | Large language model | Medium | Outside SR 26-2 scope (generative AI) | Chloe Morgan / Ben Carter | Production | Conditionally Approved |
| MDL-COR-010 | Onboarding Risk Classification | Machine learning | Medium | Model under SR 26-2 | Amira Duarte / Jordan Patel | Production | Approved |

## Risk rating and validation cycle

| Rating | Meaning | Full revalidation |
|---|---|---|
| High | Material reliance for regulatory compliance or customer decisions; complex or opaque method | Every 12 months |
| Medium | Supports decisions that other controls also cover | Every 24 months |
| Low | Limited reliance or easily checked output | Every 36 months |

SR 26-2 sets no fixed validation frequency. The bank keeps fixed cycles in MRM-POL-001 and tracks them with control CTL-04. When a model is approved, the platform sets the last validation date to the decision date and the next date by the cycle above. Changing a model's risk rating recalculates the next date.

## Documentation

Six artifacts are required: model development document, methodology and assumptions, data lineage and sources, ongoing monitoring plan, user procedures, and limitations and compensating controls. Status is derived, not typed: **Outdated** if the documentation was last reviewed more than 24 months ago, otherwise **Complete** at 100%, **Partial** at 50% or more, and **Incomplete** below that. Control CTL-09 tests that High-risk entries are Complete.

## Lifecycle and approval

Lifecycle stages: Development, Pre-Implementation Validation, Production, Under Remediation, Retired. Approval statuses: Approved, Conditionally Approved, Pending Approval, Not Approved, Approval Expired.

- New entries start as Pending Approval. Only the validation workflow or an administrator sets approval status and validation dates.
- An approved Initial validation moves the model from Development or Pre-Implementation Validation to Production.
- A rejected validation sets the model to Not Approved, and a Production model to Under Remediation.
- Archiving removes an entry from active views; it is blocked while a validation is in fieldwork or review. Archived entries are read-only until restored.

## Ongoing monitoring

Models that score records are monitored monthly (or quarterly if configured) against KPI and KRI limits that the model owner sets with a written rationale. The seed appends the range observed in the reference window to each rationale. Generative systems are monitored through the LLM evaluation suite. Methods and limits are in [VALIDATION_METHODOLOGY.md](VALIDATION_METHODOLOGY.md).

## Roles

| Role | Typical holder | Responsibilities |
|---|---|---|
| Administrator | Model Risk Technology | Platform configuration, archiving, drift simulation, overrides |
| Model owner | First-line business and analytics heads | Register and maintain their models, set thresholds, respond to findings, remediate, complete AI readiness assessments |
| Validator | Second-line model validation | Run validations independently, raise findings, verify remediation, run LLM evaluations and bias tests |
| Compliance reviewer | Head of Model Risk Management, BSA/AML Officer, AI Governance Lead | Schedule validations, approve or reject them, accept risk, extend findings, review AI assessments, decide on AI systems, maintain controls |

Owners can edit only models where they are the business owner or model risk owner. The independence rules for validation are in [VALIDATION_METHODOLOGY.md](VALIDATION_METHODOLOGY.md).

### Permission matrix

| Permission | Administrator | Model owner | Validator | Compliance reviewer |
|---|---|---|---|---|
| `ai:assess` | Yes | Yes |  |  |
| `ai:bias_test` | Yes |  | Yes |  |
| `ai:edit` | Yes | Yes |  |  |
| `ai:eval_run` | Yes |  | Yes |  |
| `ai:read` | Yes | Yes | Yes | Yes |
| `ai:review` |  |  |  | Yes |
| `ai:template_edit` | Yes |  |  | Yes |
| `audit:read` | Yes |  | Yes | Yes |
| `breach:acknowledge` | Yes | Yes | Yes |  |
| `finding:accept_risk` | Yes |  |  | Yes |
| `finding:close` |  |  | Yes |  |
| `finding:create` |  |  | Yes |  |
| `finding:extend` | Yes |  |  | Yes |
| `finding:read` | Yes | Yes | Yes | Yes |
| `finding:respond` | Yes | Yes |  |  |
| `inventory:archive` | Yes |  |  |  |
| `inventory:create` | Yes | Yes |  |  |
| `inventory:edit` | Yes | Yes |  |  |
| `inventory:read` | Yes | Yes | Yes | Yes |
| `monitoring:configure` | Yes | Yes |  |  |
| `monitoring:read` | Yes | Yes | Yes | Yes |
| `monitoring:run` | Yes | Yes | Yes |  |
| `monitoring:simulate` | Yes |  |  |  |
| `regulatory:edit` | Yes |  |  | Yes |
| `regulatory:read` | Yes | Yes | Yes | Yes |
| `regulatory:test` | Yes |  | Yes | Yes |
| `report:generate` | Yes | Yes | Yes | Yes |
| `report:read` | Yes | Yes | Yes | Yes |
| `user:admin` | Yes |  |  |  |
| `user:read` | Yes | Yes | Yes | Yes |
| `validation:approve` | Yes |  |  | Yes |
| `validation:perform` |  |  | Yes |  |
| `validation:read` | Yes | Yes | Yes | Yes |
| `validation:schedule` | Yes |  |  | Yes |

## Committees

| Committee | Pack | Focus |
|---|---|---|
| Model Risk Management Committee (MRMC) | Inventory, validation outcomes and pipeline, findings, documentation, AI summary | Whole inventory, approvals, overdue validations and findings |
| Financial Crime Model Oversight Committee (FCMOC) | Latest performance for the eight financial crime models, breaches, drift, alert volumes, Part 504 controls | Detection quality and the Part 504 program |
| AI Governance Committee (AIGC) | AI inventory, assessments awaiting review, evaluation runs, bias tests, AI controls | AI classification, approval and testing |

Each pack has a rule-based summary and recommendations built from the figures in it, and can be downloaded as a PDF from Committee Reporting.
