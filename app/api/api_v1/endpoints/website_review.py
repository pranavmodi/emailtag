"""Website candidate review endpoints — confirm, reject, and stream-batch-resolve."""

import asyncio
import json
from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, nullslast
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.pif_info import PifInfo
from app.services.website_resolution import (
    apply_website_resolution,
    persist_aliases_for_firm,
    resolve_firm_website,
)

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


@router.get("/run-batch")
async def run_batch(limit: int = 100):
    """
    Stream website resolution for up to `limit` unresolved firms as SSE.

    Emits one JSON event per firm processed. Clients connect via EventSource
    and receive rows in real time rather than waiting for the full batch.
    """
    # Snapshot the firm IDs to process up front (no long-held session).
    with SessionLocal() as db:
        rows = (
            db.query(PifInfo.id, PifInfo.firm_name)
            .filter(
                PifInfo.canonical_website.is_(None),
                PifInfo.website_candidate.is_(None),
                PifInfo.merge_status != "merged",
            )
            .order_by(
                nullslast(PifInfo.icp_score.desc()),
                nullslast(func.array_length(PifInfo.conversation_ids, 1).desc()),
            )
            .limit(limit)
            .all()
        )
    firm_ids = [(str(r.id), r.firm_name) for r in rows]
    total = len(firm_ids)

    async def event_stream():
        for i, (firm_id, firm_name) in enumerate(firm_ids):

            def process_one(fid):
                db = SessionLocal()
                try:
                    firm = db.query(PifInfo).filter(PifInfo.id == fid).first()
                    if not firm:
                        return None

                    result = resolve_firm_website(firm)

                    # Pre-check: if another firm already owns this canonical domain,
                    # demote to candidate before touching the DB (avoids flush-time
                    # UniqueViolation that would crash the SSE stream).
                    if result.canonical_website:
                        already_claimed = (
                            db.query(PifInfo.id)
                            .filter(
                                PifInfo.canonical_website == result.canonical_website,
                                PifInfo.id != firm.id,
                            )
                            .first()
                        )
                        if already_claimed:
                            result = replace(
                                result,
                                canonical_website=None,
                                website_status="pending",
                                website_source="human",
                                review_candidate=result.canonical_website,
                            )

                    apply_website_resolution(firm, result)
                    persist_aliases_for_firm(db, firm)
                    db.add(firm)
                    db.commit()
                    return result
                finally:
                    db.close()

            result = await asyncio.to_thread(process_one, firm_id)

            candidate = None
            status = "skip"
            source = None
            if result:
                status = result.website_status
                source = result.website_source
                candidate = result.review_candidate or result.canonical_website

            payload = json.dumps({
                "pif_id": firm_id,
                "firm_name": firm_name,
                "status": status,
                "candidate": candidate,
                "source": source,
                "index": i + 1,
                "total": total,
            })
            yield f"data: {payload}\n\n"

        yield f"data: {json.dumps({'done': True, 'total': total})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
