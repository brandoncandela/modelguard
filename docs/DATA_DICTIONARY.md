# Data dictionary

All records describe Candela Bank, a fictional international bank. No real customer, bank or institutional data is used. Names are random combinations of given names and syllable-built surnames; list entries are generated the same way and are not drawn from any real sanctions, PEP or watch list. Elevated and high-risk jurisdictions use ISO 3166 user-assigned codes (QM, QN, QO, XA, XB, XC) so no real country is labelled.

## How the data is generated

| Setting | Default | Effect |
|---|---|---|
| `MODELGUARD_SEED` | 20261031 | Every random draw is keyed on this seed, the purpose and the month |
| `MODELGUARD_ANCHOR_DATE` | end of last month | Last day of the latest complete month of history |
| `MODELGUARD_HISTORY_MONTHS` | 12 | Months of history; the first six are the reference window |
| `MODELGUARD_DRIFT_SCENARIO` | moderate | none, moderate (0.5) or severe (1.0) peak drift intensity |
| `MODELGUARD_DRIFT_PERIODS` | 3 | Drift ramps up over the last N months |

The same seed and anchor date always produce the same data. Each month can be regenerated on its own.

**Customers.** 1,200 customers across five segments (retail 55%, small business 20%, corporate 12%, private banking 8%, correspondent 5%). About 3% are latent launderers, more likely in risky industries, elevated jurisdictions and among PEPs. Each has one typology: structuring, rapid movement of funds, high-risk jurisdiction exposure, funnel account or trade-based layering. Some honest customers look suspicious on purpose: cash-heavy restaurants near the reporting threshold, payroll and treasury pass-through, and families with links to high-risk jurisdictions.

**Transactions.** About 5,000 a month across card, ACH, check, cash, domestic and international wires, and instant payments. Suspicious customers add typology transactions, which carry the ground truth label.

**Drift.** As intensity rises: instant payments grow, amounts inflate, and cross-border activity increases (population drift); launderers structure below the $8,000 band, pass funds through instant payments and route through elevated jurisdictions, and adverse media uses new scam vocabulary (concept drift); a payment platform migration drops counterparty countries and currency codes (data quality drift).

**Onboarding.** About 200 applications a month with related parties. Names are screened against the sanctions, PEP and watch lists; a few are deliberate spelling variants of list entries (true matches) and some are namesakes (false positives).

**Adverse media.** About 520 synthetic news snippets a month about screened names, written from templates. Some are about a different person with the same name and read exactly like a true hit.

**Dispositions.** Investigators escalate about 92% of productive alerts and 7% of others; SARs follow most escalated productive alerts.

## Volumes (default seed)

| Table | Rows |
|---|---|
| customers | 1,200 |
| transactions | 64,997 |
| applications | 2,460 |
| media_articles | 6,240 |
| watchlist_entries | 900 |
| alerts | 8,139 |
| scored_records | 180,974 |
| monitoring_runs | 108 |
| validations / findings | 12 / 29 |
| ai_systems / llm_eval_cases | 10 / 24 |
| regulatory_sources / requirements / controls | 9 / 40 / 21 |

## Inventory and monitoring

**models**

| Column | Meaning |
|---|---|
| model_id | Business key, format MDL-XXX-000 |
| name, description | |
| business_owner_id, model_risk_owner_id | Users with the model owner role |
| business_unit, category, methodology, methodology_type, vendor, version, developer, geographies | Descriptive fields |
| risk_rating, risk_rationale | High, Medium or Low, with the reason |
| supervisory_classification, classification_rationale | Whether SR 26-2 / OCC 2026-13 treats the entry as a model: model, outside the definition (deterministic) or outside the scope (generative AI) |
| lifecycle_stage | Development, Pre-Implementation Validation, Production, Under Remediation, Retired |
| implementation_date, last_validation_date, next_validation_date | |
| approval_status | Approved, Conditionally Approved, Pending Approval, Not Approved, Approval Expired |
| documentation_checklist, documentation_reviewed_on, documentation_status | Six required artifacts; status derived (Outdated after 24 months, Complete, Partial at 50% or more, Incomplete) |
| limitations | Known limitations |
| monitoring_frequency | Monthly or Quarterly |
| is_archived, archived_at, archived_reason | Soft delete |

**model_thresholds**: model_id, metric, kind (KPI or KRI), direction (min: lower is adverse; max: higher is adverse), warning_limit, breach_limit, rationale (includes the range observed in the reference window), is_active.

**scored_records**: one row per record a model scored. model_id, period (YYYY-MM), record_ref (transaction, application name, article, customer or alert ID), score, predicted (alerted or rated high), actual (synthetic ground truth), escalated (investigator decision, for alerted records), segment, dq_issue (first data quality rule failed), scenario.

**alerts**: alert_id, model_id, period, created_on, subject_ref, customer_id, score, rule_hits, priority, disposition, escalated, sar_filed, is_productive.

**transactions**: txn_id, customer_id, booking_date, period, amount_usd, currency, channel, direction, counterparty_name, counterparty_country, is_suspicious, typology, dq_issue, scenario.

**customers**: customer_id, name, segment, country, nationality_region (synthetic, used for disparity testing only), industry, onboarding_date, pep_flag, expected_monthly_volume, risk_score and risk_rating (latest month), is_suspicious, typology.

**applications**: application_id, period, applicant_name, related_parties, segment, country, nationality_region, industry, ownership_layers, expected_monthly_volume, cash_intensive, source_of_funds_documented, is_high_risk (ground truth), dq_issue.

**monitoring_runs**: run_id, model_id, period, reference_start, reference_end, record_count, reference_count, scenario, triggered_by, is_latest (false once re-run), run_at, overall_status.

**metric_results**: run_id, model_id, period, metric, value (null when undefined), numerator, denominator, warning_limit, breach_limit, direction, status, details (confusion matrix, PSI bins, data quality rule counts).

**feature_drift**: run_id, feature, feature_type, psi, test_name, statistic, p_value, effect_size, drift_flag, drift_level, details (bins).

**breaches**: breach_id, run_id, model_id, period, metric, value, limits, direction, level (Warning or Breach), severity, consecutive_periods, severity_rationale, status (Open, Acknowledged, Resolved), acknowledged_by, notes.

## Validation and findings

**validations**: validation_id, model_id, validation_type (Initial, Periodic, Change / Targeted), status, scope_areas, scope_notes, lead_validator_id, team, independence_attested, independence_statement, scheduled_start, scheduled_end, actual_start, submitted_on, decided_on, overall_rating, summary, conditions.

**validation_approvals**: validation_id, approver_id, decision, comments, conditions, decided_at.

**findings**: finding_id, validation_id, model_id, title, description, category, severity, status, raised_by_id, raised_on, management_response, action_plan, remediation_owner_id, target_date, original_target_date, extension_count, closed_on, closed_by_id, risk_acceptance_rationale, risk_acceptance_expiry.

**evidence**: evidence_id, entity_type (validation, finding, control), entity_id, title, evidence_type, description, file_name, content_type, file_size, sha256, storage_key, uploaded_by_id, uploaded_at.

**workflow_events**: entity_type, entity_id, event_type, from_status, to_status, actor_id, comment, data, occurred_at.

## AI governance

**ai_systems**: system_id, name, linked_model_id, use_case, business_justification, business_unit, model_owner_id, system_owner_id, ai_technique, provider, deployment_status, data_sources, intended_use, prohibited_use, affects_natural_persons, interacts_with_public, human_oversight, oversight_description, explainability_rating, explainability_notes, bias_testing_status, bias_testing_summary, performance_monitoring, hallucination_evaluation, limitations, internal_risk_tier, eu_ai_act_class, approval_status, approved_on, next_review_date.

**assessment_templates / assessment_questions**: template name, version, framework; question code, category, text, guidance, reference (article), weight, classification_trigger, is_active, order.

**ai_assessments / assessment_responses**: assessment_id, ai_system_id, template_id, status, assessor_id, reviewer_id, derived_classification, category_scores, overall_score, gaps, review_comments; per question answer (Yes, Partial, No, N/A) and evidence_note.

**llm_eval_cases**: case_id, ai_system_id, category, prompt, context, expected_behavior (answer or refuse), expected_facts, allowed_references, consistency_group.

**llm_recorded_responses**: case_id, model_version, response_text, reviewer_decision (Accepted, Edited, Overridden), planted_defects (used only by tests of the evaluator).

**llm_eval_runs / llm_eval_results**: run metrics and threshold results; per case facts found, claims, unsupported claims, hallucinated references, policy violations, behaviour check, normalised answer, pass or fail.

**bias_test_results**: ai_system_id, attribute, reference_group, groups (rates, ratios, p-values, flags), min_ratio, min_fpr_ratio, passed, records, periods, method.

## Regulatory and audit

**regulatory_sources**: source_id, short_name, title, issuer, source_type (Regulation, Supervisory guidance, Internal policy), citation, url, published_on, last_reviewed_on, status (Current, In force, Superseded, Rescinded), superseded_by, superseded_on, applicability, notes.

**regulatory_requirements**: requirement_id, source_id, section, summary (paraphrased), obligation_type, theme.

**controls**: control_id, name, description, control_type, frequency, owner_id, evidence_requirement, implementation_status, last_reviewed_on, next_review_on, identified_gaps, remediation_actions, automated_test, documentation_refs. Linked to requirements and models through `control_requirements` and `control_models`.

**control_test_results**: control_id, test_name, result (Pass or Fail), population, exceptions, exception_items, summary, run_by, run_at.

**audit_events**: event_id, occurred_at, actor_username, actor_role, action, entity_type, entity_ref, summary, changes (JSON diff), request_id, ip_address, prev_hash, hash. Append-only.

**reports**: report_id, report_type, title, as_of, generated_by_id, generated_at, file_name, file_size, sha256, storage_key.
