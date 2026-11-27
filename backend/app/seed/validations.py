"""Seeded validation history: 12 validations (every workflow status) and 29 findings.

Dates are day offsets from the data anchor and line up with each model's inventory record
(last and next validation dates). Workflow events carry their historical dates; the audit trail
records the import itself, since the history predates the platform.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryModel
from app.models.monitoring import MetricResult, MonitoringRun
from app.models.users import User
from app.models.validation import Finding, Validation, ValidationApproval, WorkflowEvent
from app.services import audit
from app.services.validation import TARGET_DAYS, store_evidence

ALL_SCOPE = ["Conceptual soundness", "Data integrity and lineage", "Implementation and process verification",
             "Outcomes analysis and back-testing", "Benchmarking", "Ongoing monitoring review",
             "Threshold and tuning review", "Documentation review"]

VALIDATIONS = [
    dict(key="TM_PRIOR", model="MDL-TM-001", type="Periodic", status="Conditionally Approved", lead="nbrooks",
         team=["tlindgren"], start=-470, end=-400, submitted=-395, decided=-380, approver="hmarsh",
         rating="Needs improvement", scope=ALL_SCOPE,
         summary="Scenario logic is implemented as documented and the alert-to-case process works. Below-the-line "
                 "sampling found structuring activity just under the scenario band, counterparty country is "
                 "missing on part of the cross-border feed, and the rapid movement scenario ignores instant payments.",
         conditions="Remediate {F02} and {F04} within nine months, and report scenario recall monthly to the "
                    "Financial Crime Model Oversight Committee until both are closed."),
    dict(key="SF", model="MDL-SF-002", type="Periodic", status="Approved", lead="tlindgren", team=[],
         start=-300, end=-245, submitted=-240, decided=-230, approver="hmarsh",
         rating="Satisfactory with recommendations", scope=ALL_SCOPE[:4] + ["Threshold and tuning review"],
         summary="Matching engine reproduces list hits on a seeded test deck of transliterated and truncated names. "
                 "Threshold benchmarking was completed during the validation. One medium finding on concatenated "
                 "names from ISO 20022 fields remains in remediation."),
    dict(key="CRS", model="MDL-CRS-004", type="Periodic", status="Conditionally Approved", lead="nbrooks", team=[],
         start=-220, end=-160, submitted=-158, decided=-150, approver="hmarsh", rating="Needs improvement",
         scope=["Conceptual soundness", "Data integrity and lineage", "Outcomes analysis and back-testing",
                "Documentation review"],
         summary="The points model is transparent and consistently applied, but factor weights rest on expert "
                 "judgement, expected activity values are stale for legacy customers, and the High rating captures "
                 "under half of customers later linked to suspicious activity.",
         conditions="Provide statistical support for factor weights ({F09}) and refresh expected activity for "
                    "legacy customers ({F10}) before the next periodic review."),
    dict(key="PEP", model="MDL-PEP-005", type="Periodic", status="Approved", lead="tlindgren", team=[],
         start=-360, end=-310, submitted=-305, decided=-300, approver="dosei", rating="Satisfactory",
         scope=["Conceptual soundness", "Outcomes analysis and back-testing", "Threshold and tuning review"],
         summary="PEP matching performs within tolerance on the sample deck. Transliterated names are the main "
                 "weakness and are covered by one medium finding."),
    dict(key="AM", model="MDL-AM-006", type="Periodic", status="Pending Review", lead="gwu", team=["nbrooks"],
         start=-50, end=-5, submitted=-6, decided=None, approver=None, rating="Needs improvement",
         scope=["Conceptual soundness", "Data integrity and lineage", "Outcomes analysis and back-testing",
                "Ongoing monitoring review", "Documentation review"],
         summary="Out-of-time testing shows recall falling on articles that describe newer scam and money mule "
                 "typologies, which the fixed vocabulary under-weights. Namesake articles cannot be separated by "
                 "the model. Training data provenance is undocumented. Retraining and documentation are required."),
    dict(key="SAD", model="MDL-SAD-007", type="Initial", status="Conditionally Approved", lead="tlindgren",
         team=["gwu"], start=-360, end=-290, submitted=-288, decided=-280, approver="hmarsh",
         rating="Satisfactory with recommendations", scope=ALL_SCOPE,
         summary="Gradient boosting model outperforms the rules on the out-of-time sample with higher precision at "
                 "comparable recall. Reason codes for investigators and retraining triggers are not yet in place.",
         conditions="Go-live approved subject to monthly recall monitoring with a breach limit of 0.78 and delivery "
                    "of investigator reason codes ({F18}) within six months."),
    dict(key="AII", model="MDL-AII-008", type="Initial", status="Rejected", lead="gwu", team=["tlindgren"],
         start=-140, end=-75, submitted=-72, decided=-60, approver="hmarsh", rating="Unsatisfactory",
         scope=["Conceptual soundness", "Implementation and process verification",
                "Outcomes analysis and back-testing", "Documentation review"],
         summary="Sampled case summaries contained fabricated facts, override reasons are not captured, and the "
                 "pilot has no testing for instructions embedded in customer documents. Not fit for production use.",
         reject="Not approved for production. Resubmit after {F21} and {F23} are remediated and the evaluation "
                "suite shows hallucination below the 2% warning limit."),
    dict(key="AII_RESUB", model="MDL-AII-008", type="Initial", status="Not Started", lead=None, team=[],
         start=None, end=None, submitted=None, decided=None, approver=None, rating=None,
         scope=["Conceptual soundness", "Outcomes analysis and back-testing", "Ongoing monitoring review"],
         summary="", notes="Re-validation after remediation of the findings from the rejected initial validation."),
    dict(key="LLM", model="MDL-LLM-009", type="Initial", status="Conditionally Approved", lead="gwu", team=[],
         start=-260, end=-210, submitted=-208, decided=-200, approver="lferreira",
         rating="Satisfactory with recommendations",
         scope=["Conceptual soundness", "Outcomes analysis and back-testing", "Documentation review"],
         summary="Answers are grounded in the approved library in most sampled cases. Citation accuracy was not "
                 "measured before the validation and usage logs are kept for 30 days only.",
         conditions="Quarterly evaluation results reported to the AI Governance Committee, and usage log "
                    "retention aligned to the record retention policy ({F25})."),
    dict(key="COR", model="MDL-COR-010", type="Periodic", status="Approved", lead="nbrooks", team=[],
         start=-170, end=-125, submitted=-124, decided=-120, approver="dosei", rating="Satisfactory",
         scope=["Conceptual soundness", "Data integrity and lineage", "Outcomes analysis and back-testing"],
         summary="Discrimination and calibration are acceptable overall. Calibration for virtual asset businesses "
                 "should be watched as that segment grows."),
    dict(key="TM_CURRENT", model="MDL-TM-001", type="Periodic", status="In Progress", lead="nbrooks",
         team=["tlindgren"], start=-40, end=20, actual=-35, submitted=None, decided=None, approver=None, rating=None,
         scope=ALL_SCOPE, summary=""),
    dict(key="NS", model="MDL-NS-003", type="Periodic", status="Scheduled", lead="tlindgren", team=[],
         start=15, end=75, submitted=None, decided=None, approver=None, rating=None,
         scope=["Conceptual soundness", "Outcomes analysis and back-testing", "Threshold and tuning review"],
         summary=""),
]

# key, validation, title, description, category, severity, status, owner, raised, target (offset or None),
# closed, response, action plan, extensions [(offset, new_target_offset, justification)], risk acceptance
FINDINGS = [
    dict(key="F01", v="TM_PRIOR", sev="High", cat="Performance", status="Closed", owner="jpatel", raised=-430,
         closed=-120, title="Structuring scenario band not supported by below-the-line testing",
         desc="Below-the-line sampling found repeated cash deposits between $7,000 and $7,999 that the $8,000 to "
              "$9,999 band does not evaluate. The band was set without testing activity just below it.",
         resp="Agreed. Below-the-line testing will be added to the annual tuning cycle.",
         plan="Run below-the-line sampling at 10% decrements, document results, and recalibrate the band."),
    dict(key="F02", v="TM_PRIOR", sev="Critical", cat="Data quality", status="In Remediation", owner="jpatel",
         raised=-428, target=-60, ext=[(-70, -10, "Payment platform vendor delayed the field mapping release; "
                                                    "interim manual enrichment in place for wires over $10,000.")],
         title="Counterparty country missing on part of the cross-border payment feed",
         desc="Reconciliation of the monitoring feed to the payment system found counterparty country blank on "
              "cross-border payments from one channel. Jurisdiction scenarios cannot evaluate those payments.",
         resp="Agreed. Root cause is a field mapping gap in the payment platform extract.",
         plan="Fix the extract mapping, backfill twelve months of history and add a completeness control."),
    dict(key="F03", v="TM_PRIOR", sev="Medium", cat="Documentation", status="Closed", owner="jpatel", raised=-420,
         closed=-250, title="Tuning rationale missing for three of seven scenarios",
         desc="Threshold values for three scenarios have no recorded rationale or approval.",
         resp="Agreed.", plan="Document rationale and approvals for all scenario thresholds."),
    dict(key="F04", v="TM_PRIOR", sev="High", cat="Conceptual soundness", status="In Remediation", owner="jpatel",
         raised=-415, target=45, ext=[(-200, 45, "Instant payments scenario requires new data feed from the "
                                                 "real-time payments hub, scheduled for Q4.")],
         title="Rapid movement scenario limited to wires; instant payments not covered",
         desc="The rapid movement scenario evaluates wire transfers only. Instant payments volume has grown since "
              "launch and pass-through activity through that channel is not monitored.",
         resp="Agreed. Instant payments were out of scope at original design.",
         plan="Extend the scenario to instant payments and run parallel testing for one quarter."),
    dict(key="F05", v="TM_PRIOR", sev="Medium", cat="Governance", status="Risk Accepted", owner="mreyes",
         raised=-410, accept=(-330, 35, "Quality assurance sampling of closed alerts provides partial coverage; "
                                         "a dedicated review is planned once the case system upgrade completes."),
         title="No periodic review of alert disposition quality",
         desc="There is no documented periodic review of whether alerts are closed correctly.",
         resp="Partially agreed. QA sampling exists but is not documented as a model control.",
         plan="Formalise QA sampling as a control after the case system upgrade."),
    dict(key="F06", v="SF", sev="High", cat="Performance", status="Closed", owner="ewalsh", raised=-285, closed=-235,
         title="Similarity threshold not benchmarked against list update samples",
         desc="The 0.80 threshold was inherited from the previous engine and was not tested against the current "
              "list and payment name formats.",
         resp="Agreed.", plan="Benchmark thresholds 0.70 to 0.90 on a seeded test deck and document the choice."),
    dict(key="F07", v="SF", sev="Medium", cat="Implementation", status="In Remediation", owner="ewalsh", raised=-270,
         target=45, title="Concatenated names from ISO 20022 fields reduce match scores",
         desc="Names truncated or concatenated during message conversion score below threshold in testing.",
         resp="Agreed.", plan="Add name splitting rules before matching and retest on the test deck."),
    dict(key="F08", v="SF", sev="Low", cat="Documentation", status="Closed", owner="ewalsh", raised=-265,
         closed=-200, title="List version control evidence incomplete",
         desc="Evidence of which list version was loaded on each date was incomplete for two months.",
         resp="Agreed.", plan="Log list version and load timestamp with each refresh."),
    dict(key="F09", v="CRS", sev="High", cat="Conceptual soundness", status="Response Submitted", owner="jpatel",
         raised=-200, target=60, title="Factor weights set by judgement without statistical support",
         desc="Behavioural factor weights were set by expert judgement and have not been tested against outcomes.",
         resp="Agreed. We will fit weights against SAR outcomes and compare discrimination.",
         plan="Fit a logistic model to outcomes, compare with current weights, and propose recalibration."),
    dict(key="F10", v="CRS", sev="Medium", cat="Data quality", status="In Remediation", owner="aduarte",
         raised=-195, target=-10, title="Expected activity values stale for legacy customers",
         desc="Expected monthly volume has not been refreshed since onboarding for customers onboarded before 2021.",
         resp="Agreed.", plan="Refresh expected activity through periodic review outreach, prioritising High risk."),
    dict(key="F11", v="CRS", sev="Medium", cat="Performance", status="Open", owner="jpatel", raised=-170, target=30,
         title="High rating captures under half of later suspicious customers",
         desc="Back-testing shows the High rating identified 44% of customers later linked to suspicious activity.",
         resp=None, plan=None),
    dict(key="F12", v="PEP", sev="Low", cat="Documentation", status="Closed", owner="ewalsh", raised=-340,
         closed=-250, title="PEP list refresh frequency not documented",
         desc="The procedure does not state how often the PEP list is refreshed.", resp="Agreed.",
         plan="Document weekly refresh and monitoring of load failures."),
    dict(key="F13", v="PEP", sev="Medium", cat="Performance", status="Pending Validation", owner="ewalsh",
         raised=-335, target=40, ext=[(-160, 40, "Transliteration library upgrade needed vendor approval.")],
         title="Recall below 80% for transliterated names in sample testing",
         desc="Sample testing on transliterated variants found 74% recall.", resp="Agreed.",
         plan="Add transliteration pairs and retest."),
    dict(key="F14", v="AM", sev="High", cat="Performance", status="Open", owner="aduarte", raised=-12, target=None,
         title="Recall degraded on emerging fraud typologies",
         desc="Out-of-time testing shows relevant articles about scams and money mule networks scored below the "
              "threshold. The vocabulary was fixed at training time.", resp=None, plan=None),
    dict(key="F15", v="AM", sev="Medium", cat="Conceptual soundness", status="Open", owner="ewalsh", raised=-11,
         target=None, title="Model cannot distinguish namesakes",
         desc="Articles about different people with the same name score as relevant. Disambiguation relies on "
              "analysts.", resp=None, plan=None),
    dict(key="F16", v="AM", sev="Low", cat="Documentation", status="Open", owner="ewalsh", raised=-10, target=None,
         title="Training data provenance not documented",
         desc="Sources and labelling process for the training articles are not documented.", resp=None, plan=None),
    dict(key="F17", v="SAD", sev="Critical", cat="Performance", status="Closed", owner="jpatel", raised=-340,
         closed=-284, title="No out-of-time back-testing before go-live",
         desc="Performance was reported on a random split only, which overstates performance on future periods.",
         resp="Agreed.", plan="Run out-of-time back-testing on the latest three months and report."),
    dict(key="F18", v="SAD", sev="High", cat="Conceptual soundness", status="In Remediation", owner="jpatel",
         raised=-330, target=-15, title="No reason codes for investigators",
         desc="Investigators receive a score with no explanation of the drivers, which slows review and weakens "
              "documentation of decisions.", resp="Agreed.",
         plan="Add feature contribution reason codes to the alert view."),
    dict(key="F19", v="SAD", sev="Medium", cat="Data quality", status="Risk Accepted", owner="mreyes", raised=-325,
         accept=(-282, 80, "Lag is inherent to SAR outcomes; quarterly label refresh mitigates. Accepted until "
                           "the case system provides interim dispositions."),
         title="Labels depend on SAR outcomes with a 90-day lag",
         desc="Training labels use SAR filing outcomes, which arrive up to 90 days after the activity.",
         resp="Partially agreed.", plan="Quarterly label refresh."),
    dict(key="F20", v="SAD", sev="High", cat="Governance", status="Response Submitted", owner="jpatel", raised=-320,
         target=40, title="Retraining triggers not defined",
         desc="There are no defined performance or drift levels that trigger retraining.",
         resp="Agreed. Triggers will be tied to the monitoring thresholds.",
         plan="Define retraining triggers on recall and PSI breaches and add them to the monitoring plan."),
    dict(key="F21", v="AII", sev="Critical", cat="Performance", status="Open", owner="bcarter", raised=-100,
         target=30, title="Fabricated case facts in sampled summaries",
         desc="In the evaluation sample, summaries stated amounts and dates that were not in the alert record.",
         resp=None, plan=None),
    dict(key="F22", v="AII", sev="High", cat="Governance", status="In Remediation", owner="bcarter", raised=-98,
         target=40, title="Override reasons not captured",
         desc="When investigators disagree with the recommendation the reason is not recorded, so override "
              "patterns cannot be analysed.", resp="Agreed.", plan="Make override reason a required field."),
    dict(key="F23", v="AII", sev="High", cat="Conceptual soundness", status="Open", owner="bcarter", raised=-95,
         target=40, title="No testing for instructions embedded in customer documents",
         desc="Customer-supplied documents are passed into the prompt and were not tested for embedded "
              "instructions that could change the recommendation.", resp=None, plan=None),
    dict(key="F24", v="LLM", sev="Medium", cat="Performance", status="Closed", owner="bcarter", raised=-240,
         closed=-205, title="Citation accuracy not measured",
         desc="No test measured whether cited sources support the answer.", resp="Agreed.",
         plan="Add citation checks to the evaluation suite."),
    dict(key="F25", v="LLM", sev="Medium", cat="Governance", status="Pending Validation", owner="bcarter",
         raised=-235, target=35, title="Usage logs kept for 30 days only",
         desc="Prompt and response logs are deleted after 30 days, below the record retention policy.",
         resp="Agreed.", plan="Extend retention to policy and confirm deletion jobs."),
    dict(key="F26", v="LLM", sev="Low", cat="Documentation", status="Closed", owner="cmorgan", raised=-230,
         closed=-210, title="User guidance does not state prohibited uses",
         desc="The user guide does not tell staff which uses are prohibited.", resp="Agreed.",
         plan="Add a prohibited uses section."),
    dict(key="F27", v="COR", sev="Medium", cat="Performance", status="Open", owner="jpatel", raised=-150, target=50,
         title="Calibration drift for virtual asset businesses",
         desc="Predicted probabilities underestimate observed high-risk rates for virtual asset applicants.",
         resp=None, plan=None),
    dict(key="F28", v="COR", sev="Low", cat="Data quality", status="Closed", owner="aduarte", raised=-148,
         closed=-126, title="Missing country codes default to medium risk",
         desc="Applications with a missing country are scored as medium jurisdiction risk without a flag.",
         resp="Agreed.", plan="Flag missing country as a data quality exception."),
    dict(key="F29", v="TM_CURRENT", sev="High", cat="Performance", status="Open", owner="jpatel", raised=-5,
         target=None, title="Scenario recall below tolerance in the latest quarter",
         desc="Monitoring shows recall below the 0.47 breach limit in the drift period, driven by structuring "
              "below the band and pass-through through instant payments.", resp=None, plan=None),
]


def _at(anchor: date, offset: int, hour: int = 10) -> datetime:
    return datetime.combine(anchor + timedelta(days=offset), time(hour, 0), tzinfo=timezone.utc)


def _ev(db, etype, eid, event_type, actor, frm, to, comment, at, data=None):
    db.add(WorkflowEvent(entity_type=etype, entity_id=eid, event_type=event_type, from_status=frm, to_status=to,
                         actor_id=actor.id, comment=comment, data=data or {}, occurred_at=at))


def metrics_csv(db: Session, model: InventoryModel, until: date) -> bytes:
    rows = db.execute(select(MetricResult.period, MetricResult.metric, MetricResult.value, MetricResult.numerator,
                             MetricResult.denominator, MetricResult.status)
                      .join(MonitoringRun, MetricResult.run_id == MonitoringRun.id)
                      .where(MetricResult.model_id == model.id, MonitoringRun.is_latest.is_(True),
                             MetricResult.period <= f"{until.year:04d}-{until.month:02d}")
                      .order_by(MetricResult.period, MetricResult.metric)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["period", "metric", "value", "numerator", "denominator", "status"])
    for r in rows:
        w.writerow([r[0], r[1], "" if r[2] is None else f"{r[2]:.6f}", r[3], r[4], r[5]])
    return buf.getvalue().encode()


def seed_validations(db: Session, anchor: date, progress) -> Dict[str, int]:
    users = {u.username: u for u in db.execute(select(User)).scalars()}
    models = {m.model_id: m for m in db.execute(select(InventoryModel)).unique().scalars()}
    admin = users["admin"]

    def d(off):
        return None if off is None else anchor + timedelta(days=off)

    # Assign IDs in date order per year
    def vdate(spec):
        return d(spec["start"]) if spec["start"] is not None else anchor + timedelta(days=30)

    order = sorted(VALIDATIONS, key=vdate)
    vid, counter = {}, {}
    for spec in order:
        y = vdate(spec).year
        counter[y] = counter.get(y, 0) + 1
        vid[spec["key"]] = f"VAL-{y}-{counter[y]:03d}"
    fid, fcount = {}, {}
    for spec in sorted(FINDINGS, key=lambda s: s["raised"]):
        y = d(spec["raised"]).year
        fcount[y] = fcount.get(y, 0) + 1
        fid[spec["key"]] = f"FND-{y}-{fcount[y]:03d}"
    fmt = {k: v for k, v in fid.items()}

    vals: Dict[str, Validation] = {}
    for spec in VALIDATIONS:
        model = models[spec["model"]]
        lead = users.get(spec["lead"]) if spec["lead"] else None
        team = [users[u].id for u in spec["team"]]
        v = Validation(validation_id=vid[spec["key"]], model_id=model.id, validation_type=spec["type"],
                       status=spec["status"], scope_areas=spec["scope"], scope_notes=spec.get("notes", ""),
                       lead_validator_id=lead.id if lead else None, team=team,
                       independence_attested=spec["status"] not in ("Not Started", "Scheduled"),
                       independence_statement=("I have no role in the development, ownership or use of this model "
                                               "and report outside the business line.")
                       if spec["status"] not in ("Not Started", "Scheduled") else "",
                       scheduled_start=d(spec["start"]), scheduled_end=d(spec["end"]),
                       actual_start=d(spec.get("actual", spec["start"])) if spec["status"] not in (
                           "Not Started", "Scheduled") else None,
                       submitted_on=d(spec["submitted"]), decided_on=d(spec["decided"]),
                       overall_rating=spec["rating"], summary=spec["summary"],
                       conditions=spec.get("conditions", "").format(**fmt),
                       created_at=_at(anchor, (spec["start"] or 0) - 20))
        db.add(v)
        db.flush()
        vals[spec["key"]] = v
        sched = users["hmarsh"]
        created_at = _at(anchor, (spec["start"] or -5) - 20)
        _ev(db, "validation", v.id, "CREATED", sched, None, "Not Started", "", created_at)
        if spec["status"] == "Not Started":
            continue
        _ev(db, "validation", v.id, "STATUS_CHANGE", sched, "Not Started", "Scheduled", "", _at(anchor, spec["start"] - 14))
        if spec["status"] == "Scheduled":
            continue
        _ev(db, "validation", v.id, "STATUS_CHANGE", lead, "Scheduled", "In Progress",
            "Independence attested", _at(anchor, spec.get("actual", spec["start"])))
        if spec["status"] == "In Progress":
            continue
        _ev(db, "validation", v.id, "STATUS_CHANGE", lead, "In Progress", "Pending Review", "", _at(anchor, spec["submitted"]))
        if spec["status"] == "Pending Review":
            continue
        approver = users[spec["approver"]]
        comment = spec.get("reject", "").format(**fmt) if spec["status"] == "Rejected" else \
            "Decision recorded at Model Risk Management Committee."
        db.add(ValidationApproval(validation_id=v.id, approver_id=approver.id, decision=spec["status"],
                                  comments=comment, conditions=v.conditions, decided_at=_at(anchor, spec["decided"], 15)))
        _ev(db, "validation", v.id, "STATUS_CHANGE", approver, "Pending Review", spec["status"], comment,
            _at(anchor, spec["decided"], 15))

    findings: Dict[str, Finding] = {}
    for spec in FINDINGS:
        v = vals[spec["v"]]
        vspec = next(s for s in VALIDATIONS if s["key"] == spec["v"])
        raiser = users[vspec["lead"]]
        validator = raiser
        owner = users[spec["owner"]]
        raised = d(spec["raised"])
        policy = raised + timedelta(days=TARGET_DAYS[spec["sev"]])
        if spec.get("ext"):
            original, target = policy, d(spec["ext"][-1][1])
        else:
            original = target = d(spec["target"]) if spec.get("target") is not None else policy
        f = Finding(finding_id=fid[spec["key"]], validation_id=v.id, model_id=v.model_id, title=spec["title"],
                    description=spec["desc"], category=spec["cat"], severity=spec["sev"], status=spec["status"],
                    raised_by_id=raiser.id, raised_on=raised, management_response=spec.get("resp") or "",
                    action_plan=spec.get("plan") or "", remediation_owner_id=owner.id, target_date=target,
                    original_target_date=original,
                    extension_count=len(spec.get("ext", [])), closed_on=d(spec.get("closed")),
                    closed_by_id=validator.id if spec["status"] == "Closed" else None,
                    created_at=_at(anchor, spec["raised"]))
        if spec.get("accept"):
            off, exp, why = spec["accept"]
            f.risk_acceptance_rationale = why
            f.risk_acceptance_expiry = d(exp)
        db.add(f)
        db.flush()
        findings[spec["key"]] = f
        _ev(db, "finding", f.id, "RAISED", raiser, None, "Open", spec["desc"][:300], _at(anchor, spec["raised"]),
            {"severity": spec["sev"]})
        st = spec["status"]
        if st == "Open":
            continue
        t_resp = spec["raised"] + 12
        _ev(db, "finding", f.id, "RESPONSE", owner, "Open", "Response Submitted", spec.get("resp") or "",
            _at(anchor, t_resp), {"action_plan": spec.get("plan")})
        if st == "Response Submitted":
            continue
        if st == "Risk Accepted":
            off, exp, why = spec["accept"]
            _ev(db, "finding", f.id, "STATUS_CHANGE", users["hmarsh"], "Response Submitted", "Risk Accepted", why,
                _at(anchor, off), {"risk_acceptance_expiry": str(d(exp))})
            continue
        _ev(db, "finding", f.id, "STATUS_CHANGE", validator, "Response Submitted", "In Remediation",
            "Action plan accepted", _at(anchor, t_resp + 5))
        for (when, new_t, why) in spec.get("ext", []):
            _ev(db, "finding", f.id, "EXTENSION", users["hmarsh"], "In Remediation", "In Remediation", why,
                _at(anchor, when), {"to": str(d(new_t))})
        if st == "In Remediation":
            continue
        t_sub = (spec.get("closed") or 0) - 20 if st == "Closed" else -8
        content = (f"Remediation evidence for {f.finding_id}: {spec['title']}\n\nAction plan: {spec.get('plan')}\n"
                   f"Completed by {owner.full_name}. Synthetic record generated by the ModelGuard seed.\n").encode()
        store_evidence(db, owner, "finding", f.id, f.finding_id, "Remediation completion memo", "Remediation memo",
                       "Summary of the completed action plan", f"{f.finding_id}-remediation.txt", "text/plain",
                       content, at=_at(anchor, t_sub - 1), write_audit=False)
        _ev(db, "finding", f.id, "STATUS_CHANGE", owner, "In Remediation", "Pending Validation",
            "Remediation complete; evidence attached", _at(anchor, t_sub))
        if st == "Pending Validation":
            continue
        _ev(db, "finding", f.id, "STATUS_CHANGE", validator, "Pending Validation", "Closed",
            "Remediation verified against evidence", _at(anchor, spec["closed"]))

    # Evidence for validations past fieldwork: the validation memo and, where history exists, a metrics extract
    for spec in VALIDATIONS:
        v = vals[spec["key"]]
        if v.status in ("Not Started", "Scheduled"):
            continue
        lead = users[spec["lead"]]
        fs = [f for f in findings.values() if f.validation_id == v.id]
        memo = [f"Validation {v.validation_id}: {v.model.model_id} {v.model.name}", f"Type: {v.validation_type}",
                f"Scope: {', '.join(v.scope_areas)}", f"Rating: {v.overall_rating or 'in progress'}", "",
                v.summary or "Fieldwork in progress.", "", "Findings:"]
        memo += [f"  {f.finding_id} [{f.severity}] {f.title}" for f in fs] or ["  none"]
        when = spec.get("submitted") or -3
        store_evidence(db, lead, "validation", v.id, v.validation_id, "Validation working memo", "Validation memo",
                       "Scope, conclusions and findings", f"{v.validation_id}-memo.txt", "text/plain",
                       "\n".join(memo).encode(), at=_at(anchor, when - 1), write_audit=False)
        until = d(spec.get("submitted") or 0)
        csv_bytes = metrics_csv(db, v.model, until)
        if csv_bytes.count(b"\n") > 1:
            store_evidence(db, lead, "validation", v.id, v.validation_id, "Outcomes analysis extract",
                           "Back-testing data", "Monthly monitoring metrics up to the submission date",
                           f"{v.validation_id}-outcomes.csv", "text/csv", csv_bytes, at=_at(anchor, when - 2),
                           write_audit=False)
    audit.record(db, admin.username, admin.role, "SEED_VALIDATION_HISTORY", "dataset", "validations",
                 f"Imported {len(vals)} validations and {len(findings)} findings with their workflow history",
                 {"validations": sorted(vid.values()), "findings": len(findings)})
    progress(f"validation history: {len(vals)} validations, {len(findings)} findings")
    return {"validations": len(vals), "findings": len(findings)}
