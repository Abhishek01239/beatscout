"""Automation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Automation, User
from ..schemas.automation import AutomationCreate, AutomationOut, AutomationPatch, AutomationRunResponse
from .deps import get_current_user

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("", response_model=list[AutomationOut])
def list_automations(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return db.query(Automation).filter(Automation.user_id == current.id).all()


@router.post("/create", response_model=AutomationOut)
def create_automation(body: AutomationCreate, db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    automation = Automation(user_id=current.id, **body.model_dump())
    db.add(automation)
    from datetime import datetime, timedelta, timezone
    automation.next_run_at = datetime.now(timezone.utc) + \
        timedelta(hours=automation.discovery_frequency_hours)
    db.commit()
    db.refresh(automation)
    return automation


@router.patch("/{automation_id}", response_model=AutomationOut)
def update_automation(automation_id: int, body: AutomationPatch,
                      db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    automation = db.get(Automation, automation_id)
    if automation is None or automation.user_id != current.id:
        raise HTTPException(404, "Automation not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(automation, field, value)
    db.commit()
    db.refresh(automation)
    return automation


@router.delete("/{automation_id}")
def delete_automation(automation_id: int, db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    automation = db.get(Automation, automation_id)
    if automation is None or automation.user_id != current.id:
        raise HTTPException(404, "Automation not found")
    db.delete(automation)
    db.commit()
    return {"deleted": True}


@router.post("/{automation_id}/run", response_model=AutomationRunResponse)
def run_now(automation_id: int, db: Session = Depends(get_db),
            current: User = Depends(get_current_user)):
    from ..services.automation import run_automation
    automation = db.get(Automation, automation_id)
    if automation is None or automation.user_id != current.id:
        raise HTTPException(404, "Automation not found")
    try:
        result = run_automation(db, automation, current.id)
    except PermissionError:
        raise HTTPException(403, "Rights verification failed during automation run.")
    return result