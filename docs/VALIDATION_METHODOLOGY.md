# Validation and monitoring methodology

## Validation workflow

| Status | Who moves it on | Prerequisites |
|---|---|---|
| Not Started | Administrator or compliance reviewer schedules | Lead validator, scope areas, start and end dates |
| Scheduled | Lead validator starts fieldwork | Lead and team independent of the model; independence attested |
| In Progress | Lead validator submits for review | Overall rating, a summary of at least 50 characters, at least one evidence item |
| Pending Review | Compliance reviewer or administrator decides | Approver not on the validation team and not an owner of the model |
| Approved | | No open Critical or High findings from this validation |
| Conditionally Approved | | Written conditions (20+ characters); blocked by Critical findings still Open with no accepted plan |
| Rejected | | A written reason |

A reviewer can also return a validation from Pending Review to In Progress with a comment. One validation can be active per model. Planning fields are editable by Model Risk Management before fieldwork; fieldwork fields only by the validation team during fieldwork.

**Independence.** Validators must hold the validator role and must not be the model's business owner or model risk owner. The approver must not have worked on the validation and must not own the model. Control CTL-05 retests these rules across every validation.

**Scope areas.** Conceptual soundness; data integrity and lineage; implementation and process verification; outcomes analysis and back-testing; benchmarking; ongoing monitoring review; threshold and tuning review; documentation review. These follow the components of validation in SR 26-2 Section V (conceptual soundness, outcomes analysis, ongoing monitoring) and the testing elements of 3 NYCRR 504.3.

**Ratings.** Satisfactory; Satisfactory with recommendations; Needs improvement; Unsatisfactory.

**Evidence.** Files up to 10 MB in PDF, CSV, TXT, JSON, PNG, JPG, XLSX or DOCX. Each file is stored by its SHA-256, which is shown in the app and in the validation report. Downloads re-check the hash.

## Findings lifecycle

| From | To | Who | Rule |
|---|---|---|---|
| Open | Response Submitted | Model owner or remediation owner | Management response, action plan, owner, target date within policy |
| Response Submitted | In Remediation | Validator (not an owner) | Accepts the plan |
| Response Submitted | Open | Validator | Rejects the response with a reason |
| In Remediation | Pending Validation | Remediation owner | At least one remediation evidence item |
| Pending Validation | Closed | Validator who did not remediate | Verifies the evidence |
| Pending Validation | In Remediation | Validator | Rejects the remediation with a reason |
| Open, Response Submitted or In Remediation | Risk Accepted | Compliance reviewer or administrator | Rationale of 20+ characters, expiry within 12 months; never for Critical findings |

Default target dates by severity: Critical 60 days, High 90, Medium 180, Low 270. Extensions need a compliance reviewer or administrator and a justification of 20+ characters; a third extension needs an administrator. A finding is overdue when it is open and its target date has passed. Aging buckets: not due, 1 to 30, 31 to 90 and over 90 days past target. Every step is written to the finding's history and to the audit trail.

## Monitoring metrics

All metrics are computed from `scored_records` for the period against the reference window (the first six months of history). Undefined ratios are reported as missing, never as zero.

| Metric | Formula | Applies to |
|---|---|---|
| Precision | TP / (TP + FP) | All scoring models |
| Recall | TP / (TP + FN) | All scoring models |
| F1 | 2PR / (P + R) | All scoring models |
| False-positive rate | FP / (FP + TN); FP / alerts reported alongside | All scoring models |
| Alert rate | Alerts / records | All scoring models |
| Alert conversion | Escalated alerts / alerts | Alerting models |
| Override rate | Decisions differing from recommendation / decisions | AI triage |
| Score PSI | See below | All scoring models |
| Max feature PSI | Largest PSI across monitored inputs | Models with input features |
| Data quality exceptions | Records failing an input rule / records | All scoring models |

**Ground truth.** Recall and precision use the synthetic ground truth label on every record. A bank cannot see the suspicious activity it missed; in practice recall is estimated with below-the-line testing, look-backs and SAR back-testing, and precision with investigation outcomes. Alert conversion uses recorded investigator decisions, not ground truth.

### Population Stability Index

PSI = sum over bins of (a - e) x ln(a / e), where e is the reference share and a the current share. Numeric scores use ten bins cut at the reference deciles with open outer bins. Scores with 20 or fewer distinct values (the rules engine, whose scores are mostly zero) are binned by value, because decile edges collapse. Categorical inputs use one bin per category. Empty bins are floored at 0.0001. Bands, by industry convention rather than regulation: under 0.10 stable, 0.10 to 0.25 moderate shift, 0.25 or more significant shift.

### Input drift tests

Each monitored input is tested with PSI and a hypothesis test: two-sample Kolmogorov-Smirnov for numeric inputs (effect size D) and chi-square homogeneity for categorical inputs (effect size Cramer's V). With thousands of records a test can be significant for a trivial shift, so drift is flagged only when it is material:

- Significant: PSI 0.25 or more, or p < 0.01 with effect 0.20 or more
- Moderate: PSI 0.10 or more, or p < 0.01 with effect 0.10 or more
- Stable: otherwise

Monitored inputs: amount, channel, counterparty jurisdiction tier and direction (transactions); expected volume, ownership layers, industry, segment and country tier (applications); monthly volume, cash share and transaction count (customer activity); article length; and source model (AI triage).

### Data quality rules

| Feed | Rule | Description |
|---|---|---|
| transactions | `missing_amount` | Amount is null |
| transactions | `non_positive_amount` | Amount is zero or negative |
| transactions | `invalid_currency` | Currency is not a valid ISO 4217 code used by the bank |
| transactions | `missing_counterparty_country` | Counterparty country missing on a non-cash payment |
| transactions | `unknown_counterparty_country` | Counterparty country not in the jurisdiction reference table |
| transactions | `booking_date_outside_period` | Booking date falls outside the reporting period |
| applications | `missing_country` | Applicant country missing |
| applications | `missing_industry` | Industry missing for a business applicant |
| applications | `non_positive_volume` | Expected monthly volume is zero or negative |
| articles | `empty_body` | Article body empty or not parsed |

## Thresholds and breach severity

Each threshold has a warning and a breach limit. For "min" metrics lower values are adverse; for "max" metrics higher values are adverse. The warning limit must sit on the safe side of the breach limit, and the API rejects any pair that does not.

| Level | Rule |
|---|---|
| Low | Past the warning limit, within the breach limit |
| Medium | Past the breach limit by less than one warning-to-breach band |
| High | Past the breach limit by one band or more |
| Escalation | One level up (Medium to High, High to Critical) when the breach has persisted 2+ consecutive periods on a High-risk model, or 3+ on any model |

Only the latest period's result is open for each metric: when a new run evaluates the metric, earlier open records close as "returned within limits" or "superseded". Changing thresholds does not rewrite history; re-running monitoring for a period supersedes the earlier run and keeps it in run history.

### Seeded thresholds

| Model | Metric | Type | Adverse when | Warning | Breach |
|---|---|---|---|---|---|
| MDL-TM-001 | Recall | KPI | below | 52% | 47% |
| MDL-TM-001 | Precision | KPI | below | 15% | 11% |
| MDL-TM-001 | Alert conversion | KPI | below | 18% | 13% |
| MDL-TM-001 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-TM-001 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-TM-001 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-SAD-007 | Recall | KPI | below | 85% | 78% |
| MDL-SAD-007 | Precision | KPI | below | 55% | 45% |
| MDL-SAD-007 | Alert conversion | KPI | below | 45% | 35% |
| MDL-SAD-007 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-SAD-007 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-SAD-007 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-SF-002 | Recall | KPI | below | 75% | 65% |
| MDL-SF-002 | False-positive rate | KRI | above | 18% | 25% |
| MDL-SF-002 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-SF-002 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-SF-002 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-NS-003 | Recall | KPI | below | 70% | 55% |
| MDL-NS-003 | False-positive rate | KRI | above | 10% | 15% |
| MDL-NS-003 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-NS-003 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-NS-003 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-PEP-005 | Recall | KPI | below | 65% | 55% |
| MDL-PEP-005 | Precision | KPI | below | 35% | 25% |
| MDL-PEP-005 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-PEP-005 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-PEP-005 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-AM-006 | Recall | KPI | below | 90% | 80% |
| MDL-AM-006 | Precision | KPI | below | 70% | 60% |
| MDL-AM-006 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-AM-006 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-AM-006 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-CRS-004 | Recall | KPI | below | 35% | 28% |
| MDL-CRS-004 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-CRS-004 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-CRS-004 | DQ exceptions | KRI | above | 15% | 25% |
| MDL-COR-010 | Recall | KPI | below | 40% | 30% |
| MDL-COR-010 | Precision | KPI | below | 30% | 22% |
| MDL-COR-010 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-COR-010 | Max feature PSI | KRI | above | 0.10 | 0.25 |
| MDL-COR-010 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-AII-008 | Recall | KPI | below | 85% | 78% |
| MDL-AII-008 | Override rate | KRI | above | 22% | 28% |
| MDL-AII-008 | Score PSI | KRI | above | 0.10 | 0.25 |
| MDL-AII-008 | DQ exceptions | KRI | above | 1.0% | 3.0% |
| MDL-AII-008 | Factual accuracy | KPI | below | 95% | 90% |
| MDL-AII-008 | Hallucination rate | KRI | above | 2.0% | 5.0% |
| MDL-AII-008 | Policy compliance | KPI | below | 100% | 95% |
| MDL-LLM-009 | Factual accuracy | KPI | below | 95% | 90% |
| MDL-LLM-009 | Hallucination rate | KRI | above | 2.0% | 5.0% |
| MDL-LLM-009 | Unsupported claims | KRI | above | 5.0% | 10% |
| MDL-LLM-009 | Policy compliance | KPI | below | 100% | 95% |
| MDL-LLM-009 | Consistency | KPI | below | 95% | 90% |
| MDL-LLM-009 | Override rate | KRI | above | 15% | 25% |

## Model operating parameters

Transaction monitoring (MDL-TM-001) sums rule weights to a 0 to 100 score and alerts at 50 or above:

| Rule | Description | Weight |
|---|---|---|
| TM-R1 | Cash structuring: deposit of $8,000-$9,999 with 2+ such deposits in 7 days | 55 |
| TM-R2 | Funnel activity: 4+ cash deposits totalling $15,000+ in 7 days | 50 |
| TM-R3 | International wire of $5,000+ to a high-risk jurisdiction | 55 |
| TM-R4 | Rapid movement: outgoing wire of $10,000+ covered 80%+ by inflows in the prior 4 days | 55 |
| TM-R5 | Round-amount international wire of $25,000+ | 35 |
| TM-R6 | Velocity modifier: 8+ transactions in 7 days | 10 |
| TM-R7 | Customer risk modifier: static risk score of 45+ | 15 |

Other operating points: sanctions filtering alerts at similarity 0.80, name screening at 0.85, PEP identification at 0.86, the customer risk score rates High at 45 and Medium at 30, onboarding refers to EDD at probability 0.25, the adverse media classifier at 0.50, and the gradient boosting model at the 97.5th percentile of reference-window scores. `GET /api/v1/monitoring/methodology` returns these values along with the fitted model details.
