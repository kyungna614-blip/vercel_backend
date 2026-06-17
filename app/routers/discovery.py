import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.discovery import (
    discover_via_platform, import_from_csv_rows,
    list_discovery_queue, list_qualified,
)

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.get("/queue")
def discovery_queue(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    creators = list_discovery_queue(db, skip, limit)
    return [_c(c) for c in creators]


@router.get("/qualified")
def qualified_leads(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    creators = list_qualified(db, skip, limit)
    return [_c(c) for c in creators]


@router.post("/search")
def platform_search(
    platform: str = Form(...),
    query: str = Form(...),
    actor: str = Form("internal"),
    db: Session = Depends(get_db),
):
    try:
        return discover_via_platform(db, platform, query, actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Platform search failed: {e}")


@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    actor: str = Form("internal"),
    db: Session = Depends(get_db),
):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    result = import_from_csv_rows(db, rows, actor=actor)
    return result


def _c(c) -> dict:
    return {
        "id": c.id, "handle": c.handle, "platform": c.platform,
        "display_name": c.display_name, "follower_count": c.follower_count,
        "niche": c.niche or [], "status": c.status,
        "engagement_score": c.engagement_score,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
