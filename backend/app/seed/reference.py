"""Reference governance data for Candela Bank (fictional): staff, model inventory and thresholds.

Dates are offsets in days from the data anchor (the last day of the latest complete month), so the
inventory stays internally consistent whenever the seed is run.
"""
from __future__ import annotations

from app.core.enums import DOCUMENTATION_ARTIFACTS

# username, full name, role, title, business unit
USERS = [
    ("admin", "Avery Collins", "admin", "Model Risk Technology Lead", "Model Risk Management"),
    ("hmarsh", "Helen Marsh", "compliance_reviewer", "Head of Model Risk Management", "Model Risk Management"),
    ("dosei", "Daniel Osei", "compliance_reviewer", "BSA/AML Officer", "Financial Crime Compliance"),
    ("lferreira", "Lucia Ferreira", "compliance_reviewer", "AI Governance Lead", "Enterprise Risk"),
    ("nbrooks", "Nadia Brooks", "validator", "Lead Model Validator, Financial Crime", "Model Risk Management"),
    ("tlindgren", "Tomas Lindgren", "validator", "Senior Quantitative Validator", "Model Risk Management"),
    ("gwu", "Grace Wu", "validator", "AI and NLP Validation Specialist", "Model Risk Management"),
    ("jpatel", "Jordan Patel", "model_owner", "Head of Transaction Monitoring Analytics", "Financial Crime Analytics"),
    ("mreyes", "Marcus Reyes", "model_owner", "Head of Financial Crime Operations", "Financial Crime Operations"),
    ("skim", "Sofia Kim", "model_owner", "Head of Sanctions Compliance", "Sanctions Compliance"),
    ("ewalsh", "Ethan Walsh", "model_owner", "Director, Screening Analytics", "Sanctions Compliance"),
    ("aduarte", "Amira Duarte", "model_owner", "Head of KYC and Customer Risk", "Client Onboarding"),
    ("bcarter", "Ben Carter", "model_owner", "Head of Compliance AI Engineering", "Compliance Technology"),
    ("cmorgan", "Chloe Morgan", "model_owner", "Head of Compliance Advisory", "Compliance"),
]

DEMO_LOGINS = {"admin": "admin", "model_owner": "jpatel", "validator": "nbrooks", "compliance_reviewer": "hmarsh"}


def _docs(missing=()):
    return {a: a not in missing for a in DOCUMENTATION_ARTIFACTS}


# Each dict is one inventory record. Offsets: impl / last_val / next_val / doc_review are days from anchor.
MODELS = [
    dict(
        model_id="MDL-TM-001", name="AML Transaction Monitoring Scenarios",
        description="Post-execution monitoring of customer transactions using seven configured detection scenarios.",
        business_owner="mreyes", model_risk_owner="jpatel", developer="Transaction Monitoring Analytics",
        business_unit="Financial Crime Operations", category="Transaction Monitoring",
        methodology="Five detection scenarios (structuring, funnel activity, high-risk jurisdiction wires, rapid "
                    "movement of funds, round-amount international wires) with two risk modifiers. Rule weights are "
                    "summed to a 0-100 score; an alert is raised at 50 or above.",
        methodology_type="Rules-based", vendor="Vendor platform, scenarios configured in-house", version="4.3",
        geographies=["United States", "United Kingdom", "European Union", "Singapore"], risk_rating="High",
        risk_rationale="Primary control for suspicious activity detection; regulatory reliance under 3 NYCRR 504.3(a).",
        supervisory_classification="Outside SR 26-2 definition (deterministic)",
        classification_rationale="Deterministic scenario rules with no statistical, economic or financial theory, which the April 2026 guidance excludes from its model definition. Still inventoried, validated and monitored under MRM-POL-001, and validated as part of the transaction monitoring program under 3 NYCRR 504.3(a).",
        lifecycle_stage="Production", impl=-2100, last_val=-380, next_val=-15,
        approval_status="Conditionally Approved", docs=_docs(["Ongoing monitoring plan"]), doc_review=-300,
        limitations="Rapid movement scenario only evaluates wire transfers; instant payments are not covered. "
                    "Structuring scenario watches the $8,000-$9,999 band only. Rule thresholds were last tuned on "
                    "data that predates the instant payments launch.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-SF-002", name="Sanctions Payment Filtering",
        description="Real-time screening of cross-border payment counterparties against the sanctions list.",
        business_owner="skim", model_risk_owner="ewalsh", developer="Screening Analytics",
        business_unit="Sanctions Compliance", category="Sanctions Filtering",
        methodology="Names are normalised, token-sorted and compared with character 2-3 gram TF-IDF cosine "
                    "similarity against every list entry. Payments scoring 0.80 or above are held for review.",
        methodology_type="Fuzzy name matching", vendor="In-house", version="3.1",
        geographies=["Global"], risk_rating="High",
        risk_rationale="Interdiction control for prohibited transactions; regulatory reliance under 3 NYCRR 504.3(b).",
        supervisory_classification="Outside SR 26-2 definition (deterministic)",
        classification_rationale="Deterministic name-similarity scoring classified by Model Risk Management as outside the model definition. Tested as part of the filtering program under 3 NYCRR 504.3(b) and governed under MRM-POL-001. Classification reviewed annually.",
        lifecycle_stage="Production", impl=-1800, last_val=-230, next_val=135,
        approval_status="Approved", docs=_docs(), doc_review=-200,
        limitations="Similarity scoring has no date-of-birth or country corroboration, so near-miss namesakes "
                    "generate most alerts. Concatenated names from message truncation reduce match scores.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-NS-003", name="Customer and Related-Party Name Screening",
        description="Screening of onboarding applicants and related parties against sanctions and internal watch lists.",
        business_owner="skim", model_risk_owner="ewalsh", developer="Screening Analytics",
        business_unit="Sanctions Compliance", category="Name Screening",
        methodology="Same matching engine as MDL-SF-002 against the combined sanctions and watch list; alert "
                    "threshold 0.85 similarity.",
        methodology_type="Fuzzy name matching", vendor="In-house", version="2.4",
        geographies=["Global"], risk_rating="High",
        risk_rationale="Onboarding control for sanctioned and watch-listed parties.",
        supervisory_classification="Outside SR 26-2 definition (deterministic)",
        classification_rationale="Same matching engine as MDL-SF-002; governed under MRM-POL-001 and the filtering program.",
        lifecycle_stage="Production", impl=-1500, last_val=-335, next_val=30,
        approval_status="Approved", docs=_docs(), doc_review=-330,
        limitations="Related parties are screened only when captured at onboarding; ownership changes after "
                    "onboarding rely on periodic review.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-CRS-004", name="Customer Risk Rating Model",
        description="Monthly customer risk score combining static profile factors with recent account behaviour.",
        business_owner="aduarte", model_risk_owner="jpatel", developer="Transaction Monitoring Analytics",
        business_unit="Client Onboarding", category="Customer Risk Rating",
        methodology="Points model: segment, industry, booking jurisdiction and PEP status (static) plus cash "
                    "intensity, high-risk jurisdiction exposure, volume against expected activity and near-threshold "
                    "cash deposits (behavioural). Score 45+ is High, 30-45 Medium.",
        methodology_type="Statistical scoring", vendor="In-house", version="2.0",
        geographies=["United States", "United Kingdom", "European Union", "Singapore"], risk_rating="High",
        risk_rationale="Drives due diligence intensity and periodic review frequency for every customer.",
        supervisory_classification="Model under SR 26-2",
        classification_rationale="Quantitative scoring that produces risk estimates used for due diligence decisions; treated as a model.",
        lifecycle_stage="Production", impl=-1300, last_val=-150, next_val=215,
        approval_status="Conditionally Approved", docs=_docs(["Methodology and assumptions"]), doc_review=-500,
        limitations="Factor weights were set by expert judgement and have not been statistically fitted. Expected "
                    "activity values are stale for legacy customers.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-PEP-005", name="PEP Identification",
        description="Identifies politically exposed persons among applicants and related parties.",
        business_owner="skim", model_risk_owner="ewalsh", developer="Screening Analytics",
        business_unit="Sanctions Compliance", category="PEP Screening",
        methodology="Fuzzy matching against the PEP list with an alert threshold of 0.86 similarity.",
        methodology_type="Fuzzy name matching", vendor="In-house", version="1.6",
        geographies=["Global"], risk_rating="Medium",
        risk_rationale="Feeds enhanced due diligence; secondary to the onboarding risk model.",
        supervisory_classification="Outside SR 26-2 definition (deterministic)",
        classification_rationale="Deterministic name-similarity scoring; governed under MRM-POL-001.",
        lifecycle_stage="Production", impl=-1400, last_val=-300, next_val=430,
        approval_status="Approved", docs=_docs(), doc_review=-290,
        limitations="Family members and close associates are identified only when listed as related parties.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-AM-006", name="Adverse Media Relevance Classifier",
        description="Ranks news articles retrieved for screened names by relevance to financial crime.",
        business_owner="aduarte", model_risk_owner="ewalsh", developer="Screening Analytics",
        business_unit="Client Onboarding", category="Adverse Media Screening",
        methodology="TF-IDF over word unigrams and bigrams with logistic regression (balanced class weights). "
                    "Articles scoring 0.5 or above go to analyst review.",
        methodology_type="NLP classification", vendor="In-house", version="1.2",
        geographies=["Global"], risk_rating="Medium",
        risk_rationale="Supports onboarding and periodic review decisions; analysts review every alert.",
        supervisory_classification="Model under SR 26-2",
        classification_rationale="Statistical text classifier (non-generative machine learning), which the April 2026 guidance covers.",
        lifecycle_stage="Production", impl=-700, last_val=-760, next_val=-30,
        approval_status="Approval Expired", docs=_docs(["Data lineage and sources", "Ongoing monitoring plan"]),
        doc_review=-760,
        limitations="Cannot tell namesakes apart. Vocabulary is fixed at training time, so new typology terms "
                    "are under-weighted until retraining.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-SAD-007", name="ML Suspicious Activity Detection",
        description="Gradient boosting model that scores every transaction for suspicious activity alongside the rules.",
        business_owner="mreyes", model_risk_owner="jpatel", developer="Transaction Monitoring Analytics",
        business_unit="Financial Crime Operations", category="Suspicious Activity Detection",
        methodology="HistGradientBoostingClassifier on 14 transaction and customer features (amount, channel, "
                    "jurisdiction risk, 7-day cash and velocity windows, inflow cover). Operating threshold is the "
                    "97.5th percentile of reference-window scores.",
        methodology_type="Machine learning", vendor="In-house", version="1.1",
        geographies=["United States", "United Kingdom"], risk_rating="High",
        risk_rationale="Generates alerts for investigation; opaque method requires explainability controls.",
        supervisory_classification="Model under SR 26-2",
        classification_rationale="Non-generative machine learning model producing probability estimates.",
        lifecycle_stage="Production", impl=-240, last_val=-280, next_val=85,
        approval_status="Conditionally Approved", docs=_docs(), doc_review=-250,
        limitations="Trained on six months of labelled history; patterns absent from training (for example "
                    "pass-through via instant payments) are scored low. No reason codes for investigators.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-AII-008", name="AI-Assisted AML Investigation Triage",
        description="LLM assistant that summarises alert evidence and recommends escalate or close for investigators.",
        business_owner="mreyes", model_risk_owner="bcarter", developer="Compliance AI Engineering",
        business_unit="Financial Crime Operations", category="AI-Assisted Investigations",
        methodology="Retrieval of alert, customer and transaction facts into a fixed prompt; a hosted large "
                    "language model drafts a case summary and a recommendation with a confidence score. An "
                    "investigator makes every decision.",
        methodology_type="Large language model", vendor="Third-party foundation model, in-house orchestration",
        version="0.9", geographies=["United States"], risk_rating="High",
        risk_rationale="Influences investigator decisions on suspicious activity; generative output can be wrong.",
        supervisory_classification="Outside SR 26-2 scope (generative AI)",
        classification_rationale="Generative AI is outside the scope of the April 2026 guidance (footnote 3). Governed under AI-POL-002, the EU AI Act readiness assessment and MRM-POL-001.",
        lifecycle_stage="Pre-Implementation Validation", impl=None, last_val=None, next_val=45,
        approval_status="Not Approved", docs=_docs(["User procedures", "Limitations and compensating controls"]),
        doc_review=-90,
        limitations="Pilot only. Recommendations in this environment are simulated from seeded probabilities, "
                    "not produced by a live model. Summaries can omit or misstate facts.",
        monitoring_frequency="Monthly",
    ),
    dict(
        model_id="MDL-LLM-009", name="LLM Compliance Research Assistant",
        description="Internal assistant that answers regulatory questions from an approved knowledge base with citations.",
        business_owner="cmorgan", model_risk_owner="bcarter", developer="Compliance AI Engineering",
        business_unit="Compliance", category="LLM Compliance Research",
        methodology="Retrieval-augmented generation over an approved library of regulations and internal policy. "
                    "Answers must cite sources from the library.",
        methodology_type="Large language model", vendor="Third-party foundation model, in-house orchestration",
        version="1.2", geographies=["United States", "European Union"], risk_rating="Medium",
        risk_rationale="Research aid only; outputs are not used for customer decisions.",
        supervisory_classification="Outside SR 26-2 scope (generative AI)",
        classification_rationale="Generative AI is outside the scope of the April 2026 guidance (footnote 3). Governed under AI-POL-002 and MRM-POL-001.",
        lifecycle_stage="Production", impl=-200, last_val=-200, next_val=530,
        approval_status="Conditionally Approved", docs=_docs(), doc_review=-190,
        limitations="Monitored through the deterministic evaluation suite, not through scored records. Can "
                    "produce fluent answers with wrong citations.",
        monitoring_frequency="Quarterly",
    ),
    dict(
        model_id="MDL-COR-010", name="Onboarding Risk Classification",
        description="Classifies new applicants as standard or high risk to route enhanced due diligence.",
        business_owner="aduarte", model_risk_owner="jpatel", developer="Transaction Monitoring Analytics",
        business_unit="Client Onboarding", category="Onboarding Risk Classification",
        methodology="Logistic regression on industry and jurisdiction risk, ownership layers, cash intensity, "
                    "source-of-funds documentation, expected volume, segment and screening hits. Probability 0.25 "
                    "or above routes to EDD.",
        methodology_type="Machine learning", vendor="In-house", version="2.2",
        geographies=["United States", "United Kingdom", "European Union", "Singapore"], risk_rating="Medium",
        risk_rationale="Routes applicants to EDD; errors are caught by periodic review.",
        supervisory_classification="Model under SR 26-2",
        classification_rationale="Logistic regression producing probability estimates; treated as a model.",
        lifecycle_stage="Production", impl=-900, last_val=-120, next_val=610,
        approval_status="Approved", docs=_docs(), doc_review=-110,
        limitations="Missing country codes default to medium jurisdiction risk. Virtual asset businesses are "
                    "under-represented in training data.",
        monitoring_frequency="Monthly",
    ),
]

# metric: (kind, direction, warning, breach, rationale). The seed appends the range observed in the
# reference window to each rationale, so the documented basis always matches the data.
_STD = {
    "psi": ("KRI", "max", 0.10, 0.25, "Industry convention: under 0.10 stable, 0.10-0.25 moderate shift, 0.25+ significant."),
    "max_feature_psi": ("KRI", "max", 0.10, 0.25, "Largest input feature PSI; same bands as score PSI."),
    "dq_exception_rate": ("KRI", "max", 0.010, 0.030, "Share of scored records failing input data quality rules."),
}

THRESHOLDS = {
    "MDL-TM-001": {
        "recall": ("KPI", "min", 0.52, 0.47, "Detection rate of suspicious transactions; rules are expected to miss some typologies."),
        "precision": ("KPI", "min", 0.15, 0.11, "Share of alerts that are productive; below 0.11 alert quality is unacceptable."),
        "alert_conversion_rate": ("KPI", "min", 0.18, 0.13, "Share of alerts investigators escalate to a case."),
        **_STD,
    },
    "MDL-SAD-007": {
        "recall": ("KPI", "min", 0.85, 0.78, "Approved at go-live on the condition that recall stays above 0.78."),
        "precision": ("KPI", "min", 0.55, 0.45, "Share of model alerts that are productive."),
        "alert_conversion_rate": ("KPI", "min", 0.45, 0.35, "Investigator escalation of model alerts."),
        **_STD,
    },
    "MDL-SF-002": {
        "recall": ("KPI", "min", 0.75, 0.65, "Seeded true matches; small monthly counts make recall noisy, so the band is wide."),
        "false_positive_rate": ("KRI", "max", 0.18, 0.25, "Share of non-matching payments held for review."),
        **_STD,
    },
    "MDL-NS-003": {
        "recall": ("KPI", "min", 0.70, 0.55, "Small monthly positive counts; tolerance set wide."),
        "false_positive_rate": ("KRI", "max", 0.10, 0.15, "Share of non-matching names alerted."),
        **_STD,
    },
    "MDL-PEP-005": {
        "recall": ("KPI", "min", 0.65, 0.55, "Share of true PEP variants identified."),
        "precision": ("KPI", "min", 0.35, 0.25, "Share of PEP alerts that are true PEPs."),
        **_STD,
    },
    "MDL-AM-006": {
        "recall": ("KPI", "min", 0.90, 0.80, "Share of relevant adverse media surfaced to analysts."),
        "precision": ("KPI", "min", 0.70, 0.60, "Share of surfaced articles that are relevant."),
        **_STD,
    },
    "MDL-CRS-004": {
        "recall": ("KPI", "min", 0.35, 0.28, "Share of suspicious customers rated High."),
        "psi": _STD["psi"], "max_feature_psi": _STD["max_feature_psi"],
        "dq_exception_rate": ("KRI", "max", 0.15, 0.25, "Customers with at least one upstream transaction defect."),
    },
    "MDL-COR-010": {
        "recall": ("KPI", "min", 0.40, 0.30, "Share of high-risk applicants routed to EDD."),
        "precision": ("KPI", "min", 0.30, 0.22, "Share of EDD referrals that are high risk."),
        **_STD,
    },
    "MDL-AII-008": {
        "recall": ("KPI", "min", 0.85, 0.78, "Share of productive alerts the assistant recommended escalating."),
        "override_rate": ("KRI", "max", 0.22, 0.28, "Investigator decisions that differ from the recommendation."),
        "psi": _STD["psi"],
        "dq_exception_rate": _STD["dq_exception_rate"],
        "factual_accuracy": ("KPI", "min", 0.95, 0.90, "Case facts present in summaries (LLM evaluation suite)."),
        "hallucination_rate": ("KRI", "max", 0.02, 0.05, "Summaries with fabricated identifiers or references."),
        "policy_compliance": ("KPI", "min", 1.00, 0.95, "No tipping-off, injection-following or PII leakage."),
    },
    "MDL-LLM-009": {
        "factual_accuracy": ("KPI", "min", 0.95, 0.90, "Expected facts present in answers."),
        "hallucination_rate": ("KRI", "max", 0.02, 0.05, "Responses with a fabricated citation or identifier."),
        "unsupported_claim_rate": ("KRI", "max", 0.05, 0.10, "Factual sentences not grounded in sources."),
        "policy_compliance": ("KPI", "min", 1.00, 0.95, "Responses with no policy violation."),
        "response_consistency": ("KPI", "min", 0.95, 0.90, "Paraphrase groups that give the same answer."),
        "override_rate": ("KRI", "max", 0.15, 0.25, "Reviewer overrides of the answer."),
    },
}
