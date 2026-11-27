"""Regulatory source library, requirements and the bank's control library.

Requirement summaries are paraphrases, not quotations, and were checked against the published sources
on SOURCES_CHECKED_ON. Internal policies (MRM-POL-001, AI-POL-002, FCC-STD-003) belong to the fictional
Candela Bank. Mapping a control to a requirement records the bank's view of which control addresses it;
it does not mean the requirement is met.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryModel
from app.models.regulatory import Control, RegulatoryRequirement, RegulatorySource
from app.models.users import User
from app.services import audit

SOURCES_CHECKED_ON = date(2026, 11, 25)

SOURCES = [
    dict(source_id="SR-26-2", short_name="SR 26-2 / OCC 2026-13",
         title="Supervisory Guidance on Model Risk Management (revised interagency guidance)",
         issuer="Federal Reserve Board, OCC and FDIC", source_type="Supervisory guidance",
         citation="Federal Reserve SR 26-2; OCC Bulletin 2026-13; FDIC financial institution letter, 17 April 2026",
         url="https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm", published_on=date(2026, 4, 17),
         status="Current",
         applicability="Expected to be most relevant to banking organizations with over $30 billion in total assets. "
                       "Does not set enforceable standards; supervisory action can still follow from unsafe or "
                       "unsound practices. Generative and agentic AI models are outside its scope.",
         notes="Defines a model as a complex quantitative method applying statistical, economic or financial "
               "theories; excludes deterministic rule-based processes. Supersedes SR 11-7 and SR 21-8."),
    dict(source_id="SR-11-7", short_name="SR 11-7",
         title="Supervisory Guidance on Model Risk Management", issuer="Federal Reserve Board",
         source_type="Supervisory guidance", citation="Federal Reserve SR letter 11-7, 4 April 2011",
         url="https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm", published_on=date(2011, 4, 4),
         status="Superseded", superseded_by="SR 26-2 / OCC 2026-13", superseded_on=date(2026, 4, 17),
         applicability="Historical. Kept because MRM-POL-001 was originally built on it and older validation "
                       "reports cite it.", notes=""),
    dict(source_id="OCC-2011-12", short_name="OCC 2011-12",
         title="Sound Practices for Model Risk Management: Supervisory Guidance on Model Risk Management",
         issuer="Office of the Comptroller of the Currency", source_type="Supervisory guidance",
         citation="OCC Bulletin 2011-12, 4 April 2011",
         url="https://www.occ.gov/static/rescinded-bulletins/bulletin-2011-12.pdf", published_on=date(2011, 4, 4),
         status="Rescinded", superseded_by="OCC Bulletin 2026-13", superseded_on=date(2026, 4, 17),
         applicability="Historical. Transmitted the same interagency guidance as SR 11-7.", notes=""),
    dict(source_id="SR-21-8", short_name="SR 21-8 / OCC 2021-19",
         title="Interagency Statement on Model Risk Management for Bank Systems Supporting BSA/AML Compliance",
         issuer="Federal Reserve Board, OCC and FDIC, in consultation with FinCEN and NCUA",
         source_type="Supervisory guidance", citation="Federal Reserve SR 21-8 (9 April 2021); OCC Bulletin 2021-19",
         url="https://www.federalreserve.gov/supervisionreg/srletters/SR2108.htm", published_on=date(2021, 4, 9),
         status="Superseded", superseded_by="SR 26-2 / OCC 2026-13", superseded_on=date(2026, 4, 17),
         applicability="Historical. Addressed how model risk principles relate to BSA/AML systems.", notes=""),
    dict(source_id="NYCRR-504", short_name="3 NYCRR Part 504",
         title="Banking Division Transaction Monitoring and Filtering Program Requirements and Certifications",
         issuer="New York State Department of Financial Services", source_type="Regulation",
         citation="3 NYCRR Part 504 (effective 1 January 2017)",
         url="https://www.dfs.ny.gov/industry_guidance/transaction_monitoring", published_on=date(2016, 6, 30),
         status="In force",
         applicability="Applies to the bank's New York branch as a DFS-regulated institution.",
         notes="Annual certification due 15 April for the prior calendar year."),
    dict(source_id="EU-AIA", short_name="EU AI Act",
         title="Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence, as amended by "
               "Regulation (EU) 2026/1744", issuer="European Parliament and Council of the European Union",
         source_type="Regulation", citation="Regulation (EU) 2024/1689; Regulation (EU) 2026/1744",
         url="https://eur-lex.europa.eu/eli/reg/2024/1689/oj", published_on=date(2024, 7, 12),
         status="In force",
         applicability="Applies to AI systems the bank deploys in the EU. Obligations apply in phases: prohibited "
                       "practices and AI literacy since 2 February 2025; Annex III high-risk obligations from "
                       "2 December 2027 under Regulation (EU) 2026/1744. Check the consolidated text for other dates.",
         notes="Credit scoring of natural persons is Annex III high-risk; AI used to detect financial fraud is "
               "excluded from that point."),
    dict(source_id="MRM-POL-001", short_name="MRM-POL-001",
         title="Model Risk Management Policy v5.0", issuer="Candela Bank (fictional) Model Risk Management",
         source_type="Internal policy", citation="MRM-POL-001 v5.0, approved 30 June 2026", url="",
         published_on=date(2026, 6, 30), status="Current",
         applicability="All models and model-like tools, including deterministic rules engines and generative AI, "
                       "whatever their classification under SR 26-2.",
         notes="Updated after SR 26-2 to keep fixed revalidation cycles and lifecycle controls for every entry."),
    dict(source_id="AI-POL-002", short_name="AI-POL-002", title="AI Use and Governance Standard v1.3",
         issuer="Candela Bank (fictional) Enterprise Risk", source_type="Internal policy",
         citation="AI-POL-002 v1.3, approved 15 March 2026", url="", published_on=date(2026, 3, 15),
         status="Current", applicability="All AI systems, including generative AI outside the scope of SR 26-2.",
         notes=""),
    dict(source_id="FCC-STD-003", short_name="FCC-STD-003", title="Financial Crime Detection Tuning Standard v2.1",
         issuer="Candela Bank (fictional) Financial Crime Compliance", source_type="Internal policy",
         citation="FCC-STD-003 v2.1", url="", published_on=date(2025, 9, 1), status="Current",
         applicability="Transaction monitoring scenarios and screening thresholds.", notes=""),
]

# requirement_id, source_id, section, theme, summary (paraphrased)
REQUIREMENTS = [
    ("SR262-SCOPE", "SR-26-2", "Section II, Purpose and Scope", "Scope and definition",
     "Apply a risk-based approach tailored to the model risk profile. A model is a complex quantitative method "
     "using statistical, economic or financial theories; simple calculations and deterministic rule-based processes "
     "are excluded, and generative and agentic AI are outside scope."),
    ("SR262-MAT", "SR-26-2", "Section III, Overview of Model Risk", "Risk tiering",
     "Assess model risk from inherent risk and materiality (exposure and purpose), for individual models and in "
     "aggregate across shared data, assumptions and methods."),
    ("SR262-CHAL", "SR-26-2", "Section III, Overview of Model Risk", "Independence",
     "Effective challenge by objective experts with the expertise, independence and standing to effect change."),
    ("SR262-DEV", "SR-26-2", "Section IV, Model Development and Model Use", "Development and use",
     "Development aligned to a clear statement of purpose with testing such as out-of-sample and out-of-time "
     "testing; models used within their intended purpose with limitations understood."),
    ("SR262-VAL", "SR-26-2", "Section V, Model Validation and Monitoring", "Validation",
     "Validation assesses reliability and limitations, including conceptual soundness and outcomes analysis. It "
     "generally occurs before first use; earlier use needs attention to limitations and compensating controls."),
    ("SR262-MON", "SR-26-2", "Section V, Ongoing Model Monitoring", "Monitoring",
     "Ongoing monitoring evaluates whether models perform as expected as products, clients, data and conditions "
     "change, with procedures for responding to deterioration."),
    ("SR262-GOV", "SR-26-2", "Section VI, Governance and Controls", "Governance",
     "Policies, procedures and clear roles with accountability, including managing conflicts between development "
     "and validation; internal audit evaluates whether model risk management is effective."),
    ("SR262-INV", "SR-26-2", "Section VI, Model Inventory", "Inventory",
     "Maintain an inventory of models in development or use with enough information to understand model risk "
     "individually and in aggregate."),
    ("SR262-DOC", "SR-26-2", "Section VI, Documentation", "Documentation",
     "Documentation that supports continuity and the tracking of recommendations, responses, exceptions and "
     "remediation."),
    ("SR262-VEND", "SR-26-2", "Section VII, Vendor and Other Third-Party Products", "Third-party models",
     "Vendor and third-party models remain subject to validation, ongoing monitoring and outcomes analysis; "
     "customisations are documented and evaluated."),
    ("SR117-VAL", "SR-11-7", "Section V, Model Validation", "Validation",
     "Validation by staff with appropriate incentives, competence and influence, covering conceptual soundness, "
     "ongoing monitoring and outcomes analysis."),
    ("SR117-REV", "SR-11-7", "Section V, Model Validation", "Validation",
     "Periodic review of each model, at least annually, to confirm it is working as intended."),
    ("SR117-INV", "SR-11-7", "Section VI, Governance, Policies, and Controls", "Inventory",
     "Comprehensive inventory of models in use, under development or recently retired."),
    ("SR117-DOC", "SR-11-7", "Section VI, Governance, Policies, and Controls", "Documentation",
     "Documentation detailed enough that parties unfamiliar with a model understand how it works and its "
     "limitations."),
    ("OCC1112-ALL", "OCC-2011-12", "Attachment", "Validation",
     "Same interagency model risk management guidance as SR 11-7, applied to national banks and federal savings "
     "associations."),
    ("SR218-BSA", "SR-21-8", "Statement", "Scope and definition",
     "Model risk management principles may be appropriate considerations for BSA/AML systems without requiring a "
     "particular framework."),
    ("504-TM", "NYCRR-504", "§ 504.3(a)", "Transaction monitoring",
     "Risk-based transaction monitoring program with documented detection scenarios, thresholds and assumptions, "
     "end-to-end pre- and post-implementation testing (including scenario logic and model validation), alert "
     "investigation protocols and ongoing analysis of scenario relevance."),
    ("504-FILT", "NYCRR-504", "§ 504.3(b)", "Filtering",
     "Risk-based filtering program to interdict transactions prohibited by OFAC, which may use fuzzy matching, with "
     "end-to-end testing, ongoing analysis of logic and performance, and documentation of design."),
    ("504-DATA", "NYCRR-504", "§ 504.3(c)", "Data integrity",
     "Identify all data sources; validate data integrity, accuracy and quality; ensure complete and accurate "
     "extraction and loading; governance, qualified personnel and training."),
    ("504-REM", "NYCRR-504", "§ 504.3(d)", "Remediation",
     "Document areas needing material improvement and the remedial efforts planned and under way, available for "
     "inspection by the Superintendent."),
    ("504-CERT", "NYCRR-504", "§ 504.4", "Certification",
     "Annual board resolution or senior officer compliance finding filed by 15 April."),
    ("AIA-ART4", "EU-AIA", "Article 4", "AI literacy", "Ensure staff dealing with AI systems have sufficient AI literacy."),
    ("AIA-ART5", "EU-AIA", "Article 5", "Prohibited practices",
     "Do not place on the market or use AI practices prohibited by Article 5, including emotion recognition in "
     "the workplace except for medical or safety reasons."),
    ("AIA-ART6", "EU-AIA", "Article 6 and Annex III", "Classification",
     "Classify systems against the high-risk categories, including credit scoring of natural persons (fraud "
     "detection excluded)."),
    ("AIA-ART10", "EU-AIA", "Article 10", "Data governance",
     "High-risk systems use training, validation and test data subject to data governance, including examination "
     "for possible biases."),
    ("AIA-ART12", "EU-AIA", "Article 12", "Record keeping",
     "High-risk systems allow automatic recording of events (logs) over their lifetime."),
    ("AIA-ART13", "EU-AIA", "Article 13", "Transparency",
     "High-risk systems come with instructions for use describing capabilities and limitations."),
    ("AIA-ART14", "EU-AIA", "Article 14", "Human oversight",
     "High-risk systems are designed for effective human oversight, including the ability to override or stop them."),
    ("AIA-ART15", "EU-AIA", "Article 15", "Accuracy and robustness",
     "High-risk systems achieve appropriate accuracy, robustness and cybersecurity, with declared accuracy metrics."),
    ("AIA-ART26", "EU-AIA", "Article 26", "Deployer obligations",
     "Deployers of high-risk systems assign competent human oversight, monitor operation and keep automatically "
     "generated logs for at least six months."),
    ("AIA-ART27", "EU-AIA", "Article 27", "Fundamental rights",
     "Certain deployers, including for credit scoring of natural persons, perform a fundamental rights impact "
     "assessment before use."),
    ("AIA-ART50", "EU-AIA", "Article 50", "Transparency",
     "People are informed when they interact with an AI system, and certain AI-generated content is marked."),
    ("MRM-INV", "MRM-POL-001", "§ 3 Inventory", "Inventory",
     "Every model and model-like tool, including deterministic rules and generative AI, is inventoried, risk-rated "
     "and classified against SR 26-2."),
    ("MRM-VAL", "MRM-POL-001", "§ 5 Validation", "Validation",
     "Independent validation before production use; revalidation every 12, 24 or 36 months for High, Medium and "
     "Low risk."),
    ("MRM-MON", "MRM-POL-001", "§ 6 Monitoring", "Monitoring",
     "Monthly or quarterly monitoring against approved KPI and KRI thresholds; High and Critical breaches "
     "acknowledged within 30 days."),
    ("MRM-FND", "MRM-POL-001", "§ 7 Findings", "Remediation",
     "Target dates by severity (Critical 60, High 90, Medium 180, Low 270 days); at most two extensions; Critical "
     "findings cannot be risk-accepted."),
    ("AIP-ASSESS", "AI-POL-002", "§ 4 Assessment and approval", "Classification",
     "EU AI Act readiness assessment and AI Governance Committee approval before deployment."),
    ("AIP-EVAL", "AI-POL-002", "§ 5 Evaluation", "Accuracy and robustness",
     "Generative systems pass the LLM evaluation suite before release and quarterly after."),
    ("AIP-HUMAN", "AI-POL-002", "§ 6 Human oversight", "Human oversight",
     "Defined human oversight for AI-assisted decisions, with override reasons logged."),
    ("FCC-TUNE", "FCC-STD-003", "§ 4 Tuning", "Transaction monitoring",
     "Annual scenario tuning with below-the-line testing and documented threshold rationale."),
]

# control_id, name, type, frequency, owner, test, status, evidence, requirements, models, gaps, remediation, docs
CONTROLS = [
    ("CTL-01", "Model inventory completeness", "Governance", "Continuous", "admin", "inventory_completeness",
     "Implemented", "Inventory extract with mandatory fields; automated completeness test result.",
     ["SR262-INV", "SR117-INV", "MRM-INV"], "ALL", "", "", ["MRM-POL-001 §3"]),
    ("CTL-02", "Materiality-based risk rating", "Governance", "On change and annually", "hmarsh", None,
     "Implemented", "Risk rating rationale recorded for each inventory entry.",
     ["SR262-MAT", "MRM-INV"], "ALL", "", "", ["MRM-POL-001 §4"]),
    ("CTL-03", "Approval before production use", "Preventive", "Continuous", "hmarsh", "validation_before_use",
     "Implemented", "Validation approval record and model approval status.",
     ["SR262-VAL", "SR117-VAL", "OCC1112-ALL", "504-TM", "MRM-VAL"], "ALL",
     "Adverse media classifier remains in production with an expired approval while its revalidation is in review.",
     "Expedite review of the pending validation; interim enhanced QA on adverse media alerts.", ["MRM-POL-001 §5"]),
    ("CTL-04", "Revalidation within policy cycle", "Detective", "Monthly", "hmarsh", "revalidation_cycle",
     "Implemented", "Validation schedule against next validation dates.",
     ["SR117-REV", "MRM-VAL"], "ALL",
     "SR 26-2 sets no fixed frequency; the bank keeps fixed cycles in MRM-POL-001. Two entries are past due.",
     "Transaction monitoring revalidation in fieldwork; adverse media validation pending review.", ["MRM-POL-001 §5"]),
    ("CTL-05", "Validator and approver independence", "Preventive", "Per validation", "hmarsh",
     "validator_independence", "Implemented", "Independence attestation and approval record per validation.",
     ["SR262-CHAL", "SR117-VAL", "SR262-GOV"], "ALL", "", "", ["MRM-POL-001 §5.3"]),
    ("CTL-06", "Ongoing performance monitoring", "Detective", "Monthly", "jpatel", "monitoring_coverage",
     "Implemented", "Monitoring run history with metrics, drift tests and thresholds.",
     ["SR262-MON", "MRM-MON", "AIA-ART26"], "MONITORED", "", "", ["MRM-POL-001 §6"]),
    ("CTL-07", "Threshold breach escalation", "Detective", "Monthly", "hmarsh", "breach_escalation",
     "Implemented", "Breach register with acknowledgement notes.", ["SR262-MON", "MRM-MON"], "MONITORED", "", "",
     ["MRM-POL-001 §6.4"]),
    ("CTL-08", "Findings remediation tracking", "Detective", "Weekly", "hmarsh", "finding_timeliness",
     "Implemented", "Findings register, management responses, remediation evidence and closure by a validator.",
     ["SR262-DOC", "504-REM", "MRM-FND"], "ALL",
     "Three findings are past target, including a Critical data quality finding on transaction monitoring.",
     "Escalated to the Model Risk Management Committee with revised plans.", ["MRM-POL-001 §7"]),
    ("CTL-09", "Model documentation standards", "Preventive", "Annually", "hmarsh", "documentation_currency",
     "Partially implemented", "Documentation checklist per entry with review dates.",
     ["SR262-DOC", "SR117-DOC"], "HIGH",
     "Two High-risk entries have partial documentation (monitoring plan, methodology).",
     "Owners to complete missing artifacts before the next committee.", ["MRM-POL-001 §8"]),
    ("CTL-10", "Scenario tuning and below-the-line testing", "Detective", "Annually", "jpatel", None,
     "Partially implemented", "Tuning pack with below-the-line samples and threshold rationale.",
     ["504-TM", "FCC-TUNE", "SR262-DEV"], ["MDL-TM-001", "MDL-SAD-007"],
     "Instant payments are not covered by the rapid movement scenario; structuring below the band is not tested.",
     "Scenario extension in remediation; below-the-line testing added to the 2027 tuning cycle.", ["FCC-STD-003 §4"]),
    ("CTL-11", "Screening effectiveness testing", "Detective", "Monthly", "ewalsh", "filtering_effectiveness",
     "Implemented", "Monthly recall on seeded list matches; annual test deck results.",
     ["504-FILT"], ["MDL-SF-002", "MDL-NS-003", "MDL-PEP-005"], "", "", ["FCC-STD-003 §6"]),
    ("CTL-12", "Monitoring and filtering data integrity", "Detective", "Monthly", "jpatel", "tm_data_quality",
     "Partially implemented", "Data quality rule results by feed and month; reconciliations to source.",
     ["504-DATA"], ["MDL-TM-001", "MDL-SAD-007", "MDL-SF-002"],
     "Payment platform migration drops counterparty country and currency codes on part of the cross-border feed.",
     "Field mapping fix and backfill tracked under the Critical transaction monitoring finding.", ["FCC-STD-003 §3"]),
    ("CTL-13", "Annual Part 504 certification support", "Governance", "Annually", "dosei", None, "Implemented",
     "Certification package: program inventory, testing results, remediation log and sub-certifications.",
     ["504-CERT", "504-REM"], ["MDL-TM-001", "MDL-SF-002", "MDL-NS-003"], "", "", ["FCC-STD-003 §9"]),
    ("CTL-14", "Third-party model oversight", "Governance", "Annually", "hmarsh", None, "Partially implemented",
     "Vendor documentation, customisation log and outcomes analysis.",
     ["SR262-VEND"], ["MDL-TM-001", "MDL-AII-008", "MDL-LLM-009"],
     "Foundation model provider documentation is limited for the two generative systems.",
     "Contractual documentation request and compensating evaluation testing.", ["MRM-POL-001 §9"]),
    ("CTL-15", "AI readiness assessment before deployment", "Preventive", "Per deployment", "lferreira",
     "ai_assessment_coverage", "Implemented", "Approved EU AI Act readiness assessment per deployed system.",
     ["AIA-ART6", "AIP-ASSESS"], [], "", "", ["AI-POL-002 §4"]),
    ("CTL-16", "Prohibited practice screen", "Preventive", "Per assessment", "lferreira",
     "prohibited_practice_screen", "Implemented", "Risk classification answers and reviewer decision.",
     ["AIA-ART5"], [], "", "", ["AI-POL-002 §4.2"]),
    ("CTL-17", "Human oversight of AI-assisted decisions", "Preventive", "Continuous", "lferreira",
     "human_oversight_defined", "Partially implemented", "Oversight model per system; override logs.",
     ["AIA-ART14", "AIA-ART26", "AIP-HUMAN"], ["MDL-AII-008"],
     "Override reasons are not captured for the investigation triage pilot.",
     "Required override reason field in remediation.", ["AI-POL-002 §6"]),
    ("CTL-18", "LLM evaluation release gate", "Preventive", "Per release and quarterly", "gwu",
     "llm_evaluation_gate", "Implemented", "Evaluation run results against thresholds.",
     ["AIA-ART15", "AIP-EVAL"], ["MDL-AII-008", "MDL-LLM-009"], "", "", ["AI-POL-002 §5"]),
    ("CTL-19", "Audit trail and record keeping", "Detective", "Daily", "admin", "audit_chain_integrity",
     "Implemented", "Append-only hash-chained audit log and daily verification.",
     ["AIA-ART12", "AIA-ART26", "SR262-DOC"], "ALL", "", "", ["MRM-POL-001 §10"]),
    ("CTL-20", "AI literacy training", "Governance", "Annually", "lferreira", None, "Planned",
     "Training completion records by role.", ["AIA-ART4"], [],
     "Training not yet delivered to investigators piloting the triage assistant.",
     "Role-based training scheduled for Q1.", ["AI-POL-002 §7"]),
    ("CTL-21", "Transparency to people interacting with AI", "Preventive", "Per deployment", "lferreira", None,
     "Partially implemented", "Disclosure text and screenshots per customer-facing system.",
     ["AIA-ART50", "AIA-ART13"], [], "Customer chatbot disclosure drafted but not yet tested with users.",
     "Usability test of the disclosure before launch.", ["AI-POL-002 §8"]),
]


def seed_regulatory(db: Session, today: date, progress) -> Dict[str, int]:
    users = {u.username: u for u in db.execute(select(User)).scalars()}
    models = {m.model_id: m for m in db.execute(select(InventoryModel)).unique().scalars()}
    src = {}
    for s in SOURCES:
        obj = RegulatorySource(last_reviewed_on=SOURCES_CHECKED_ON, **s)
        db.add(obj)
        src[s["source_id"]] = obj
    db.flush()
    reqs = {}
    for rid, sid, section, theme, summary in REQUIREMENTS:
        r = RegulatoryRequirement(requirement_id=rid, source_id=src[sid].id, section=section, theme=theme,
                                  summary=summary, obligation_type=src[sid].source_type)
        db.add(r)
        reqs[rid] = r
    db.flush()
    for i, (cid, name, ctype, freq, owner, test, status, evidence, rids, mids, gaps, rem, docs) in enumerate(CONTROLS):
        c = Control(control_id=cid, name=name, description=_DESC.get(cid, name), control_type=ctype, frequency=freq,
                    owner_id=users[owner].id, evidence_requirement=evidence, implementation_status=status,
                    last_reviewed_on=today - timedelta(days=20 + (i * 7) % 90),
                    next_review_on=today + timedelta(days=150 + (i * 11) % 120), identified_gaps=gaps,
                    remediation_actions=rem, automated_test=test, documentation_refs=docs)
        c.requirements = [reqs[r] for r in rids]
        if mids == "ALL":
            c.models = list(models.values())
        elif mids == "MONITORED":
            c.models = [m for k, m in models.items() if k != "MDL-LLM-009"]
        elif mids == "HIGH":
            c.models = [m for m in models.values() if m.risk_rating == "High"]
        else:
            c.models = [models[k] for k in mids]
        db.add(c)
    db.flush()
    audit.record(db, "system", "system", "SEED_REGULATORY_LIBRARY", "dataset", "regulatory",
                 f"Loaded {len(SOURCES)} sources, {len(REQUIREMENTS)} requirements and {len(CONTROLS)} controls",
                 {"sources_checked_on": SOURCES_CHECKED_ON.isoformat()})
    progress(f"regulatory library: {len(SOURCES)} sources, {len(REQUIREMENTS)} requirements, {len(CONTROLS)} controls")
    return {"sources": len(SOURCES), "requirements": len(REQUIREMENTS), "controls": len(CONTROLS)}


_DESC = {
    "CTL-01": "Model Risk Management keeps every model and model-like tool in the inventory with owners, risk "
              "rating, SR 26-2 classification, methodology, limitations and documentation status.",
    "CTL-02": "Each entry is rated High, Medium or Low from inherent risk and materiality, with a written rationale.",
    "CTL-03": "Entries cannot move to production without an approved or conditionally approved independent validation.",
    "CTL-04": "Revalidation dates follow the policy cycle by risk rating and are tracked monthly.",
    "CTL-05": "Validators attest independence from the model; approvers cannot have worked on the validation.",
    "CTL-06": "Every scored-record model is monitored each period against approved thresholds with drift tests.",
    "CTL-07": "Threshold breaches are classified by severity; High and Critical breaches are acknowledged within 30 days.",
    "CTL-08": "Findings have owners, action plans and target dates and close only after independent verification.",
    "CTL-09": "High-risk entries maintain the six required documentation artifacts, reviewed at least every 24 months.",
    "CTL-10": "Transaction monitoring scenarios are tuned annually with below-the-line testing and documented rationale.",
    "CTL-11": "Screening recall is measured monthly on known list matches and annually on a test deck.",
    "CTL-12": "Input data for monitoring and filtering is checked against data quality rules before scoring.",
    "CTL-13": "Compliance assembles the evidence supporting the annual Part 504 board resolution or compliance finding.",
    "CTL-14": "Vendor and third-party models get the same validation and monitoring, with customisations documented.",
    "CTL-15": "AI systems complete an EU AI Act readiness assessment approved by the AI governance reviewer before deployment.",
    "CTL-16": "Risk classification questions screen for Article 5 prohibited practices; such systems are rejected.",
    "CTL-17": "Systems affecting people define who oversees them, how outputs are overridden and how overrides are logged.",
    "CTL-18": "Generative systems pass the deterministic evaluation suite before release and quarterly.",
    "CTL-19": "Material changes and approvals are written to an append-only, hash-chained audit log verified daily.",
    "CTL-20": "Staff working with AI complete role-based AI literacy training.",
    "CTL-21": "Customer-facing AI discloses that the customer is interacting with an AI system.",
}
