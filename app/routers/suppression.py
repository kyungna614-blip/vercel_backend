from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.suppression import add_suppression, is_suppressed, list_suppressions

router = APIRouter(prefix="/api/suppression", tags=["suppression"])


class SuppressionCreate(BaseModel):
    reason: str
    creator_id: Optional[str] = None
    email: Optional[str] = None
    domain: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
def add(body: SuppressionCreate, suppressed_by: str = "internal", db: Session = Depends(get_db)):
    entry = add_suppression(
        db, reason=body.reason, creator_id=body.creator_id,
        email=body.email, domain=body.domain,
        suppressed_by=suppressed_by, notes=body.notes, actor=suppressed_by,
    )
    return {"id": entry.id, "reason": entry.reason, "suppressed_at": entry.suppressed_at.isoformat()}


@router.get("")
def list_all(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    entries = list_suppressions(db, skip, limit)
    return [
        {
            "id": e.id, "creator_id": e.creator_id, "email": e.email,
            "domain": e.domain, "reason": e.reason,
            "suppressed_at": e.suppressed_at.isoformat() if e.suppressed_at else None,
            "suppressed_by": e.suppressed_by, "notes": e.notes,
        }
        for e in entries
    ]


@router.get("/check")
def check(creator_id: Optional[str] = None, email: Optional[str] = None, db: Session = Depends(get_db)):
    suppressed = is_suppressed(db, creator_id=creator_id, email=email)
    return {"is_suppressed": suppressed}
