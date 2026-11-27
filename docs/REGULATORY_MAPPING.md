# Regulatory mapping

ModelGuard maps the fictional bank's internal controls to regulatory requirements, supervisory guidance and internal policy, and tests many of those controls against live platform data. A mapping records which control the bank relies on for a requirement. It does not mean the requirement is met, and nothing in the platform guarantees compliance. Requirement summaries are paraphrases written for this project; read the source before relying on any of them.

Sources were last checked against the published text on 25 November 2026.

## What changed in 2026

The original specification for this project asked for coverage of SR 11-7 and OCC Bulletin 2011-12. Checking the agencies' sites during the build showed that on 17 April 2026 the Federal Reserve, OCC and FDIC issued revised *Supervisory Guidance on Model Risk Management*:

- Federal Reserve SR 26-2 supersedes and replaces SR 11-7 (2011) and SR 21-8 (the 2021 BSA/AML model risk statement).
- OCC Bulletin 2026-13 rescinds OCC Bulletin 2011-12, OCC Bulletin 2021-19, OCC Bulletin 1997-24 and the Comptroller's Handbook booklet *Model Risk Management*.
- The new guidance does not set enforceable standards (supervisory action can still follow from unsafe or unsound practices), is expected to be most relevant to banks with over $30 billion in assets, defines a model as a complex quantitative method applying statistical, economic or financial theories, excludes deterministic rule-based processes, and places generative and agentic AI outside its scope.

So ModelGuard keeps SR 11-7, OCC 2011-12 and SR 21-8 in the library marked Superseded or Rescinded, shows their requirements as historical references, and maps current controls to SR 26-2. The EU AI Act timeline also changed: Regulation (EU) 2026/1744 moved the Annex III high-risk obligations to 2 December 2027.

## Three kinds of obligation

| Type | Meaning in ModelGuard | Examples |
|---|---|---|
| Regulation | Binding law or rule | 3 NYCRR Part 504, EU AI Act |
| Supervisory guidance | Supervisory expectations, not enforceable standards in themselves | SR 26-2 / OCC 2026-13; superseded SR 11-7, OCC 2011-12, SR 21-8 |
| Internal policy | The fictional bank's own standards | MRM-POL-001, AI-POL-002, FCC-STD-003 |

## Sources

| Source | Type | Status | Issuer | Published | Link |
|---|---|---|---|---|---|
| SR 26-2 / OCC 2026-13 | Supervisory guidance | Current | Federal Reserve Board, OCC and FDIC | 17 Apr 2026 | [source](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm) |
| SR 11-7 | Supervisory guidance | Superseded (replaced by SR 26-2 / OCC 2026-13 on 17 Apr 2026) | Federal Reserve Board | 04 Apr 2011 | [source](https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm) |
| OCC 2011-12 | Supervisory guidance | Rescinded (replaced by OCC Bulletin 2026-13 on 17 Apr 2026) | Office of the Comptroller of the Currency | 04 Apr 2011 | [source](https://www.occ.gov/static/rescinded-bulletins/bulletin-2011-12.pdf) |
| SR 21-8 / OCC 2021-19 | Supervisory guidance | Superseded (replaced by SR 26-2 / OCC 2026-13 on 17 Apr 2026) | Federal Reserve Board, OCC and FDIC, in consultation with FinCEN and NCUA | 09 Apr 2021 | [source](https://www.federalreserve.gov/supervisionreg/srletters/SR2108.htm) |
| 3 NYCRR Part 504 | Regulation | In force | New York State Department of Financial Services | 30 Jun 2016 | [source](https://www.dfs.ny.gov/industry_guidance/transaction_monitoring) |
| EU AI Act | Regulation | In force | European Parliament and Council of the European Union | 12 Jul 2024 | [source](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) |
| MRM-POL-001 | Internal policy | Current | Candela Bank (fictional) Model Risk Management | 30 Jun 2026 | Internal (fictional) |
| AI-POL-002 | Internal policy | Current | Candela Bank (fictional) Enterprise Risk | 15 Mar 2026 | Internal (fictional) |
| FCC-STD-003 | Internal policy | Current | Candela Bank (fictional) Financial Crime Compliance | 01 Sep 2025 | Internal (fictional) |

## Requirements

| Requirement | Source | Section | Summary (paraphrased) |
|---|---|---|---|
| SR262-SCOPE | SR 26-2 / OCC 2026-13 | Section II, Purpose and Scope | Apply a risk-based approach tailored to the model risk profile. A model is a complex quantitative method using statistical, economic or financial theories; simple calculations and deterministic rule-based processes are excluded, and generative and agentic AI are outside scope. |
| SR262-MAT | SR 26-2 / OCC 2026-13 | Section III, Overview of Model Risk | Assess model risk from inherent risk and materiality (exposure and purpose), for individual models and in aggregate across shared data, assumptions and methods. |
| SR262-CHAL | SR 26-2 / OCC 2026-13 | Section III, Overview of Model Risk | Effective challenge by objective experts with the expertise, independence and standing to effect change. |
| SR262-DEV | SR 26-2 / OCC 2026-13 | Section IV, Model Development and Model Use | Development aligned to a clear statement of purpose with testing such as out-of-sample and out-of-time testing; models used within their intended purpose with limitations understood. |
| SR262-VAL | SR 26-2 / OCC 2026-13 | Section V, Model Validation and Monitoring | Validation assesses reliability and limitations, including conceptual soundness and outcomes analysis. It generally occurs before first use; earlier use needs attention to limitations and compensating controls. |
| SR262-MON | SR 26-2 / OCC 2026-13 | Section V, Ongoing Model Monitoring | Ongoing monitoring evaluates whether models perform as expected as products, clients, data and conditions change, with procedures for responding to deterioration. |
| SR262-GOV | SR 26-2 / OCC 2026-13 | Section VI, Governance and Controls | Policies, procedures and clear roles with accountability, including managing conflicts between development and validation; internal audit evaluates whether model risk management is effective. |
| SR262-INV | SR 26-2 / OCC 2026-13 | Section VI, Model Inventory | Maintain an inventory of models in development or use with enough information to understand model risk individually and in aggregate. |
| SR262-DOC | SR 26-2 / OCC 2026-13 | Section VI, Documentation | Documentation that supports continuity and the tracking of recommendations, responses, exceptions and remediation. |
| SR262-VEND | SR 26-2 / OCC 2026-13 | Section VII, Vendor and Other Third-Party Products | Vendor and third-party models remain subject to validation, ongoing monitoring and outcomes analysis; customisations are documented and evaluated. |
| SR117-VAL | SR 11-7 | Section V, Model Validation | Validation by staff with appropriate incentives, competence and influence, covering conceptual soundness, ongoing monitoring and outcomes analysis. |
| SR117-REV | SR 11-7 | Section V, Model Validation | Periodic review of each model, at least annually, to confirm it is working as intended. |
| SR117-INV | SR 11-7 | Section VI, Governance, Policies, and Controls | Comprehensive inventory of models in use, under development or recently retired. |
| SR117-DOC | SR 11-7 | Section VI, Governance, Policies, and Controls | Documentation detailed enough that parties unfamiliar with a model understand how it works and its limitations. |
| OCC1112-ALL | OCC 2011-12 | Attachment | Same interagency model risk management guidance as SR 11-7, applied to national banks and federal savings associations. |
| SR218-BSA | SR 21-8 / OCC 2021-19 | Statement | Model risk management principles may be appropriate considerations for BSA/AML systems without requiring a particular framework. |
| 504-TM | 3 NYCRR Part 504 | § 504.3(a) | Risk-based transaction monitoring program with documented detection scenarios, thresholds and assumptions, end-to-end pre- and post-implementation testing (including scenario logic and model validation), alert investigation protocols and ongoing analysis of scenario relevance. |
| 504-FILT | 3 NYCRR Part 504 | § 504.3(b) | Risk-based filtering program to interdict transactions prohibited by OFAC, which may use fuzzy matching, with end-to-end testing, ongoing analysis of logic and performance, and documentation of design. |
| 504-DATA | 3 NYCRR Part 504 | § 504.3(c) | Identify all data sources; validate data integrity, accuracy and quality; ensure complete and accurate extraction and loading; governance, qualified personnel and training. |
| 504-REM | 3 NYCRR Part 504 | § 504.3(d) | Document areas needing material improvement and the remedial efforts planned and under way, available for inspection by the Superintendent. |
| 504-CERT | 3 NYCRR Part 504 | § 504.4 | Annual board resolution or senior officer compliance finding filed by 15 April. |
| AIA-ART4 | EU AI Act | Article 4 | Ensure staff dealing with AI systems have sufficient AI literacy. |
| AIA-ART5 | EU AI Act | Article 5 | Do not place on the market or use AI practices prohibited by Article 5, including emotion recognition in the workplace except for medical or safety reasons. |
| AIA-ART6 | EU AI Act | Article 6 and Annex III | Classify systems against the high-risk categories, including credit scoring of natural persons (fraud detection excluded). |
| AIA-ART10 | EU AI Act | Article 10 | High-risk systems use training, validation and test data subject to data governance, including examination for possible biases. |
| AIA-ART12 | EU AI Act | Article 12 | High-risk systems allow automatic recording of events (logs) over their lifetime. |
| AIA-ART13 | EU AI Act | Article 13 | High-risk systems come with instructions for use describing capabilities and limitations. |
| AIA-ART14 | EU AI Act | Article 14 | High-risk systems are designed for effective human oversight, including the ability to override or stop them. |
| AIA-ART15 | EU AI Act | Article 15 | High-risk systems achieve appropriate accuracy, robustness and cybersecurity, with declared accuracy metrics. |
| AIA-ART26 | EU AI Act | Article 26 | Deployers of high-risk systems assign competent human oversight, monitor operation and keep automatically generated logs for at least six months. |
| AIA-ART27 | EU AI Act | Article 27 | Certain deployers, including for credit scoring of natural persons, perform a fundamental rights impact assessment before use. |
| AIA-ART50 | EU AI Act | Article 50 | People are informed when they interact with an AI system, and certain AI-generated content is marked. |
| MRM-INV | MRM-POL-001 | § 3 Inventory | Every model and model-like tool, including deterministic rules and generative AI, is inventoried, risk-rated and classified against SR 26-2. |
| MRM-VAL | MRM-POL-001 | § 5 Validation | Independent validation before production use; revalidation every 12, 24 or 36 months for High, Medium and Low risk. |
| MRM-MON | MRM-POL-001 | § 6 Monitoring | Monthly or quarterly monitoring against approved KPI and KRI thresholds; High and Critical breaches acknowledged within 30 days. |
| MRM-FND | MRM-POL-001 | § 7 Findings | Target dates by severity (Critical 60, High 90, Medium 180, Low 270 days); at most two extensions; Critical findings cannot be risk-accepted. |
| AIP-ASSESS | AI-POL-002 | § 4 Assessment and approval | EU AI Act readiness assessment and AI Governance Committee approval before deployment. |
| AIP-EVAL | AI-POL-002 | § 5 Evaluation | Generative systems pass the LLM evaluation suite before release and quarterly after. |
| AIP-HUMAN | AI-POL-002 | § 6 Human oversight | Defined human oversight for AI-assisted decisions, with override reasons logged. |
| FCC-TUNE | FCC-STD-003 | § 4 Tuning | Annual scenario tuning with below-the-line testing and documented threshold rationale. |

## Controls

Each control has an owner, frequency, evidence requirement, implementation status, last and next review dates, identified gaps and remediation actions, and links to the requirements and models it covers. Fifteen controls have an automated test that runs over live data and records the population tested and every exception.

| Control | Name | Owner | Status | Automated test | Requirements | Gaps |
|---|---|---|---|---|---|---|
| CTL-01 | Model inventory completeness | admin | Implemented | Inventory completeness | SR262-INV, SR117-INV, MRM-INV | - |
| CTL-02 | Materiality-based risk rating | hmarsh | Implemented | Manual | SR262-MAT, MRM-INV | - |
| CTL-03 | Approval before production use | hmarsh | Implemented | Approval before production use | SR262-VAL, SR117-VAL, OCC1112-ALL, 504-TM, MRM-VAL | Adverse media classifier remains in production with an expired approval while its revalidation is in review. |
| CTL-04 | Revalidation within policy cycle | hmarsh | Implemented | Revalidation within policy cycle | SR117-REV, MRM-VAL | SR 26-2 sets no fixed frequency; the bank keeps fixed cycles in MRM-POL-001. Two entries are past due. |
| CTL-05 | Validator and approver independence | hmarsh | Implemented | Validator and approver independence | SR262-CHAL, SR117-VAL, SR262-GOV | - |
| CTL-06 | Ongoing performance monitoring | jpatel | Implemented | Monitoring coverage | SR262-MON, MRM-MON, AIA-ART26 | - |
| CTL-07 | Threshold breach escalation | hmarsh | Implemented | Breach acknowledgement within 30 days | SR262-MON, MRM-MON | - |
| CTL-08 | Findings remediation tracking | hmarsh | Implemented | Finding remediation timeliness | SR262-DOC, 504-REM, MRM-FND | Three findings are past target, including a Critical data quality finding on transaction monitoring. |
| CTL-09 | Model documentation standards | hmarsh | Partially implemented | Documentation currency for high-risk entries | SR262-DOC, SR117-DOC | Two High-risk entries have partial documentation (monitoring plan, methodology). |
| CTL-10 | Scenario tuning and below-the-line testing | jpatel | Partially implemented | Manual | 504-TM, FCC-TUNE, SR262-DEV | Instant payments are not covered by the rapid movement scenario; structuring below the band is not tested. |
| CTL-11 | Screening effectiveness testing | ewalsh | Implemented | Screening effectiveness | 504-FILT | - |
| CTL-12 | Monitoring and filtering data integrity | jpatel | Partially implemented | Monitoring and filtering data quality | 504-DATA | Payment platform migration drops counterparty country and currency codes on part of the cross-border feed. |
| CTL-13 | Annual Part 504 certification support | dosei | Implemented | Manual | 504-CERT, 504-REM | - |
| CTL-14 | Third-party model oversight | hmarsh | Partially implemented | Manual | SR262-VEND | Foundation model provider documentation is limited for the two generative systems. |
| CTL-15 | AI readiness assessment before deployment | lferreira | Implemented | AI readiness assessment coverage | AIA-ART6, AIP-ASSESS | - |
| CTL-16 | Prohibited practice screen | lferreira | Implemented | Prohibited practice screen | AIA-ART5 | - |
| CTL-17 | Human oversight of AI-assisted decisions | lferreira | Partially implemented | Human oversight defined | AIA-ART14, AIA-ART26, AIP-HUMAN | Override reasons are not captured for the investigation triage pilot. |
| CTL-18 | LLM evaluation release gate | gwu | Implemented | LLM evaluation release gate | AIA-ART15, AIP-EVAL | - |
| CTL-19 | Audit trail and record keeping | admin | Implemented | Audit trail integrity | AIA-ART12, AIA-ART26, SR262-DOC | - |
| CTL-20 | AI literacy training | lferreira | Planned | Manual | AIA-ART4 | Training not yet delivered to investigators piloting the triage assistant. |
| CTL-21 | Transparency to people interacting with AI | lferreira | Partially implemented | Manual | AIA-ART50, AIA-ART13 | Customer chatbot disclosure drafted but not yet tested with users. |

## Coverage

For each requirement, coverage is worked out from its mapped controls:

- **Covered**: every mapped control is Implemented and its latest automated test (if any) passed
- **Partially covered**: at least one mapped control is implemented or partly implemented
- **Gap**: mapped controls exist but none is in place
- **No control mapped**: nothing is mapped
- **Historical reference**: the source is superseded or rescinded

With the default seed, 9 of 15 automated tests pass. The exceptions come from the data, not from configuration: two models past their revalidation date, three findings past target, partial documentation on High-risk entries, sanctions data quality over its limit, an AI pilot without an approved assessment, and a model in production with an expired approval.
