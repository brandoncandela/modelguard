"""Report generation, storage and retrieval. Every generated PDF is stored with its SHA-256 and audited."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, WorkflowError
from app.models.monitoring import MetricResult, MonitoringRun
from app.models.reports import Report
from app.models.users import User
from app.reporting import committee, pdf
from app.services import audit

TYPES = {"executive": "Executive Model Risk and AI Governance Report",
         "mrmc": "Model Risk Management Committee Pack",
         "fcmoc": "Financial Crime Model Oversight Committee Pack",
         "aigc": "AI Governance Committee Pack"}


def _next_id(db: Session, prefix: str) -> str:
    n = db.execute(select(func.count()).select_from(Report)).scalar()
    return f"RPT-{prefix}-{n + 1:04d}"


def _store(db: Session, user: User, report_type: str, title: str, as_of: date, report_id: str, content: bytes,
           file_name: str) -> Report:
    sha = hashlib.sha256(content).hexdigest()
    key = f"reports/{report_id}.pdf"
    path = get_settings().data_path / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    r = Report(report_id=report_id, report_type=report_type, title=title, as_of=as_of, generated_by_id=user.id,
               file_name=file_name, file_size=len(content), sha256=sha, storage_key=key)
    db.add(r)
    db.flush()
    audit.record(db, user.username, user.role, "REPORT_GENERATED", "report", report_id,
                 f"Generated {title} as of {as_of}", {"sha256": sha, "bytes": len(content), "type": report_type})
    return r


def generate_management(db: Session, user: User, report_type: str, today: date) -> Report:
    if report_type not in TYPES:
        raise WorkflowError(f"report_type must be one of {list(TYPES)}")
    packs = {c: committee.committee_pack(db, c, today) for c in committee.COMMITTEES}
    trends = committee.trends(db)
    report_id = _next_id(db, report_type.upper())
    content = pdf.render_management(report_type, report_id, packs, trends, get_settings().institution_name,
                                    f"{user.full_name} ({user.title})")
    return _store(db, user, report_type, TYPES[report_type], today, report_id, content,
                  f"{report_id}-{report_type}-{today.isoformat()}.pdf")


def _series(db: Session, model_pk: int) -> Dict[str, list]:
    rows = db.execute(select(MetricResult).join(MonitoringRun, MetricResult.run_id == MonitoringRun.id).where(
        MetricResult.model_id == model_pk, MonitoringRun.is_latest.is_(True),
        MetricResult.metric.in_(["recall", "precision"])).order_by(MetricResult.period)).scalars()
    out: Dict[str, list] = {}
    for r in rows:
        out.setdefault(r.metric, []).append({"period": r.period, "value": r.value, "breach_limit": r.breach_limit})
    return out


def generate_validation(db: Session, user: User, v_out: Dict[str, Any], model, today: date) -> Report:
    report_id = _next_id(db, "VAL")
    v = dict(v_out)
    v["as_of"] = today.isoformat()
    v["model_detail"] = {"methodology": model.methodology, "risk_rating": model.risk_rating,
                         "supervisory_classification": model.supervisory_classification,
                         "limitations": model.limitations}
    v["monitoring"] = _series(db, model.id)
    content = pdf.render_validation(report_id, v, get_settings().institution_name, f"{user.full_name} ({user.title})")
    return _store(db, user, "validation", f"Validation Report {v['validation_id']}", today, report_id, content,
                  f"{report_id}-{v['validation_id']}.pdf")


def get_file(db: Session, report_id: str):
    r = db.execute(select(Report).where(Report.report_id == report_id)).unique().scalar_one_or_none()
    if r is None:
        raise NotFound("Report not found")
    path = get_settings().data_path / r.storage_key
    if not path.exists():
        raise NotFound("Report file missing from storage; regenerate it")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != r.sha256:
        raise WorkflowError("Stored report does not match its recorded SHA-256")
    return r, data
