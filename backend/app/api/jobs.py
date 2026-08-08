"""Jobs endpoints: list, detail, enqueue, cancel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Job, User
from ..schemas.automation import JobEnqueueRequest, JobOut
from ..services.jobs import JOB_TYPES, enqueue
from .deps import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(status: str | None = None, job_type: str | None = None,
              limit: int = 100, db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    q = db.query(Job).filter(Job.user_id == current.id)
    if status:
        if status not in {"QUEUED", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED"}:
            raise HTTPException(422, "invalid job status")
        q = q.filter(Job.status == status)
    if job_type:
        q = q.filter(Job.job_type == job_type)
    return q.order_by(Job.created_at.desc()).limit(limit).all()


@router.get("/{job_id}", response_model=JobOut)
def job_detail(job_id: int, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None or job.user_id != current.id:
        raise HTTPException(404, "Job not found")
    return job


@router.post("", response_model=JobOut, status_code=202)
def create_job(body: JobEnqueueRequest, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    job = enqueue(db, user_id=current.id, job_type=body.job_type, payload=body.payload)
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None or job.user_id != current.id:
        raise HTTPException(404, "Job not found")
    if job.status in {"QUEUED", "PROCESSING"}:
        job.status = "CANCELLED"
        db.commit()
    return job


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: int, db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None or job.user_id != current.id:
        raise HTTPException(404, "Job not found")
    if job.status == "FAILED":
        job.status = "QUEUED"
        job.error = None
        db.commit()
    return job