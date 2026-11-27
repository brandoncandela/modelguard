from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.routes.validations import _read_upload, evidence_for, evidence_out, user_ref
from app.core.config import get_settings
from app.db.session import get_db
from app.models.regulatory import Control, RegulatoryRequirement
from app.models.users import User
from app.services import regulatory as svc
from app.services.validation import store_evidence

router = APIRouter(tags=["regulatory"])

DISCLAIMER = ("Control mappings record which internal controls the bank relies on for each requirement. They do not "
              "establish or guarantee compliance. Requirement text is paraphrased; consult the source.")


def source_out(s):
    return {"source_id": s.source_id, "short_name": s.short_name, "title": s.title, "issuer": s.issuer,
            "source_type": s.source_type, "citation": s.citation, "url": s.url, "published_on": s.published_on,
            "last_reviewed_on": s.last_reviewed_on, "status": s.status, "superseded_by": s.superseded_by,
            "superseded_on": s.superseded_on, "applicability": s.applicability, "notes": s.notes,
            "requirement_count": len(s.requirements)}


def control_out(db: Session, c: Control, full: bool = False):
    t = svc.latest_result(c)
    d = {"control_id": c.control_id, "name": c.name, "description": c.description, "control_type": c.control_type,
         "frequency": c.frequency, "owner": user_ref(c.owner), "evidence_requirement": c.evidence_requirement,
         "implementation_status": c.implementation_status, "last_reviewed_on": c.last_reviewed_on,
         "next_review_on": c.next_review_on, "identified_gaps": c.identified_gaps,
         "remediation_actions": c.remediation_actions, "automated_test": c.automated_test,
         "documentation_refs": c.documentation_refs,
         "requirements": [{"requirement_id": r.requirement_id, "source": r.source.short_name,
                           "source_status": r.source.status, "section": r.section, "obligation_type": r.obligation_type}
                          for r in c.requirements],
         "models": [{"model_id": m.model_id, "name": m.name} for m in c.models],
         "latest_test": None if t is None else {"result": t.result, "population": t.population,
                                                "exceptions": t.exceptions, "summary": t.summary, "run_at": t.run_at,
                                                "test_name": t.test_name}}
    if full:
        d["test_history"] = [{"result": x.result, "population": x.population, "exceptions": x.exceptions,
                              "exception_items": x.exception_items, "summary": x.summary, "run_at": x.run_at,
                              "run_by": x.run_by} for x in c.test_results[:20]]
        d["evidence"] = evidence_for(db, "control", c.id)
    return d


@router.get("/regulatory/sources")
def sources(db: Session = Depends(get_db), _: User = Depends(require("regulatory:read"))):
    return {"items": [source_out(s) for s in svc.sources(db)], "disclaimer": DISCLAIMER}


@router.get("/regulatory/requirements")
def requirements(source_id: Optional[str] = Query(None, max_length=24), db: Session = Depends(get_db),
                 _: User = Depends(require("regulatory:read"))):
    rows = svc.requirement_coverage(db)
    if source_id:
        keep = {r.requirement_id for r in db.execute(select(RegulatoryRequirement)).unique().scalars()
                if r.source.source_id == source_id}
        rows = [r for r in rows if r["requirement_id"] in keep]
    return {"items": rows, "disclaimer": DISCLAIMER}


@router.get("/regulatory/controls")
def controls(status: Optional[List[str]] = Query(None), db: Session = Depends(get_db),
             _: User = Depends(require("regulatory:read"))):
    stmt = select(Control).order_by(Control.control_id)
    if status:
        stmt = stmt.where(Control.implementation_status.in_(status))
    return {"items": [control_out(db, c) for c in db.execute(stmt).unique().scalars()], "disclaimer": DISCLAIMER}


@router.get("/regulatory/controls/{control_id}")
def control(control_id: str, db: Session = Depends(get_db), _: User = Depends(require("regulatory:read"))):
    return control_out(db, svc.get_control(db, control_id), full=True)


class ControlPatch(BaseModel):
    implementation_status: Optional[str] = None
    last_reviewed_on: Optional[date] = None
    next_review_on: Optional[date] = None
    identified_gaps: Optional[str] = Field(None, max_length=4000)
    remediation_actions: Optional[str] = Field(None, max_length=4000)
    evidence_requirement: Optional[str] = Field(None, max_length=2000)
    owner_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=4000)


@router.patch("/regulatory/controls/{control_id}")
def patch_control(control_id: str, body: ControlPatch, db: Session = Depends(get_db),
                  user: User = Depends(require("regulatory:edit"))):
    c = svc.get_control(db, control_id)
    svc.update_control(db, user, c, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(c)
    return control_out(db, c, full=True)


class TestIn(BaseModel):
    control_id: Optional[str] = Field(None, max_length=24)


@router.post("/regulatory/controls/test")
def run_tests(body: TestIn, db: Session = Depends(get_db), user: User = Depends(require("regulatory:test"))):
    results = svc.run_tests(db, (user.username, user.role), get_settings().today(), body.control_id)
    db.commit()
    return [{"control_id": r.control.control_id, "result": r.result, "population": r.population,
             "exceptions": r.exceptions, "exception_items": r.exception_items, "summary": r.summary} for r in results]


@router.post("/regulatory/controls/{control_id}/evidence", status_code=201)
async def control_evidence(control_id: str, title: str = Form(..., min_length=3, max_length=200),
                           evidence_type: str = Form(..., min_length=3, max_length=48),
                           description: str = Form("", max_length=2000), file: Optional[UploadFile] = File(None),
                           db: Session = Depends(get_db), user: User = Depends(require("regulatory:edit"))):
    c = svc.get_control(db, control_id)
    name, ctype, content = await _read_upload(file)
    ev = store_evidence(db, user, "control", c.id, c.control_id, title, evidence_type, description, name, ctype, content)
    db.commit()
    return evidence_out(ev)


@router.get("/regulatory/coverage")
def coverage(db: Session = Depends(get_db), _: User = Depends(require("regulatory:read"))):
    rows = svc.requirement_coverage(db)
    by_source = {}
    for r in rows:
        b = by_source.setdefault(r["source"], {"source": r["source"], "status": r["source_status"], "total": 0})
        b["total"] += 1
        b[r["coverage"]] = b.get(r["coverage"], 0) + 1
    controls_all = list(db.execute(select(Control)).unique().scalars())
    tests = [svc.latest_result(c) for c in controls_all if c.automated_test]
    return {"by_source": list(by_source.values()),
            "controls": {"total": len(controls_all),
                         "by_status": {s: sum(1 for c in controls_all if c.implementation_status == s)
                                       for s in ("Implemented", "Partially implemented", "Not implemented", "Planned")},
                         "automated": len(tests), "tests_passing": sum(1 for t in tests if t and t.result == "Pass")},
            "disclaimer": DISCLAIMER}
