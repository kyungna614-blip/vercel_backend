from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.campaign import Campaign
from app.services import audit as audit_svc

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    product_category: Optional[str] = None
    daily_send_limit: int = 10
    require_human_approval: bool = True


@router.post("")
def create_campaign(body: CampaignCreate, actor: str = "internal", db: Session = Depends(get_db)):
    c = Campaign(**body.model_dump(), created_by=actor)
    db.add(c)
    db.commit()
    db.refresh(c)
    audit_svc.log(db, action="campaign_created", entity_type="campaign", entity_id=c.id, actor=actor)
    return _dict(c)


@router.get("")
def list_campaigns(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Campaign)
    if status:
        q = q.filter(Campaign.status == status)
    return [_dict(c) for c in q.order_by(Campaign.created_at.desc()).all()]


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    c = db.get(Campaign, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    return _dict(c)


@router.patch("/{campaign_id}")
def update_campaign(
    campaign_id: str,
    status: Optional[str] = None,
    daily_send_limit: Optional[int] = None,
    actor: str = "internal",
    db: Session = Depends(get_db),
):
    c = db.get(Campaign, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    if status:
        c.status = status
    if daily_send_limit is not None:
        c.daily_send_limit = daily_send_limit
    db.commit()
    audit_svc.log(db, action="campaign_updated", entity_type="campaign", entity_id=campaign_id, actor=actor)
    return _dict(c)


def _dict(c: Campaign) -> dict:
    return {
        "id": c.id, "name": c.name, "description": c.description,
        "product_category": c.product_category, "status": c.status,
        "daily_send_limit": c.daily_send_limit, "total_sent": c.total_sent,
        "require_human_approval": c.require_human_approval,
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
