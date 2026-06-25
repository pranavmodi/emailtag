"""Website candidate review endpoints — confirm or reject GPT-found website candidates."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.pif_info import PifInfo

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/{pif_id}/confirm")
def confirm_website(pif_id: str, db: Session = Depends(get_db)):
    """Confirm the stored website_candidate as the canonical website for a firm."""
    firm = db.query(PifInfo).filter(PifInfo.id == pif_id).first()
    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")
    if not firm.website_candidate:
        raise HTTPException(status_code=400, detail="No candidate to confirm")

    firm.canonical_website = firm.website_candidate
    firm.website_status = "resolved"
    firm.website_source = "human_confirmed"
    firm.website_confidence = 1.0
    firm.website_candidate = None
    db.commit()
    return {"status": "ok", "canonical_website": firm.canonical_website}


@router.post("/{pif_id}/reject")
def reject_website(pif_id: str, db: Session = Depends(get_db)):
    """Reject the stored website_candidate; mark firm as having no resolvable website."""
    firm = db.query(PifInfo).filter(PifInfo.id == pif_id).first()
    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")

    firm.website_candidate = None
    firm.website_status = "none"
    db.commit()
    return {"status": "ok"}
