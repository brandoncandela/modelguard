from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.routes.validations import user_ref, validation_out
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.session import get_db
from app.models.reports import Report
from app.models.users import User
from app.reporting import committee
from app.services import reports as svc
from app.services import validation as vsvc

router = APIRouter(tags=["reporting"])


@router.get("/dashboard/executive")
def executive(db: Session = Depends(get_db), _: User = Depends(require("report:read"))):
    return committee.executive_dashboard(db, get_settings().today())


@router.get("/dashboard/trends")
def trends(db: Session = Depends(get_db), _: User = Depends(require("report:read"))):
    return committee.trends(db)


@router.get("/committees/{code}")
def committee_pack(code: str = Path(pattern="^(mrmc|fcmoc|aigc)$"), db: Session = Depends(get_db),
                   _: User = Depends(require("report:read"))):
    return committee.committee_pack(db, code, get_settings().today())


class ReportIn(BaseModel):
    report_type: str = Field(pattern="^(executive|mrmc|fcmoc|aigc)$")


def report_out(r: Report):
    return {"report_id": r.report_id, "report_type": r.report_type, "title": r.title, "as_of": r.as_of,
            "generated_by": user_ref(r.generated_by), "generated_at": r.generated_at, "file_name": r.file_name,
            "file_size": r.file_size, "sha256": r.sha256}


@router.post("/reports", status_code=201)
def generate(body: ReportIn, db: Session = Depends(get_db), user: User = Depends(require("report:generate"))):
    r = svc.generate_management(db, user, body.report_type, get_settings().today())
    db.commit()
    return report_out(r)


@router.get("/reports")
def history(db: Session = Depends(get_db), _: User = Depends(require("report:read"))):
    return [report_out(r) for r in db.execute(select(Report).order_by(Report.id.desc()).limit(100)).unique().scalars()]


@router.get("/reports/{report_id}/download")
def download(report_id: str, db: Session = Depends(get_db), _: User = Depends(require("report:read"))):
    r, data = svc.get_file(db, report_id)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{r.file_name}"',
                             "X-Content-SHA256": r.sha256})


@router.post("/validations/{validation_id}/report", tags=["validations"], status_code=201)
def validation_report(validation_id: str, db: Session = Depends(get_db),
                      user: User = Depends(require("report:generate"))):
    v = vsvc.get_validation(db, validation_id)
    if v is None:
        raise NotFound("Validation not found")
    r = svc.generate_validation(db, user, validation_out(db, v, user, full=True), v.model, get_settings().today())
    db.commit()
    return report_out(r)
