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
from app.services.firm_identity import canonical_domain
from app.services.firm_merge import FirmMergePlan, apply_firm_merge_plan
from app.services.website_resolution import (
    apply_website_resolution,
    persist_aliases_for_firm,
    resolve_firm_website,
)

router = APIRouter()


def _auto_merge_domain_clash(db, winner: PifInfo, loser: PifInfo, domain: str) -> None:
    """Merge loser into winner when both resolve to the same canonical domain."""
    plan = FirmMergePlan(
        canonical_domain=domain,
        action="auto_merge",
        confidence=0.95,
        survivor_id=str(winner.id),
        survivor_name=winner.firm_name,
        loser_ids=[str(loser.id)],
        member_ids=[str(winner.id), str(loser.id)],
        member_names=[winner.firm_name, loser.firm_name],
    )
    apply_firm_merge_plan(db, plan)


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

    # Normalize to bare domain (candidates from web search are full URLs).
    domain = canonical_domain(firm.website_candidate) or firm.website_candidate

    # If another firm already owns this domain, auto-merge (current firm is the loser).
    owner = (
        db.query(PifInfo)
        .filter(
            PifInfo.canonical_website == domain,
            PifInfo.id != firm.id,
        )
        .first()
    )
    if owner:
        _auto_merge_domain_clash(db, winner=owner, loser=firm, domain=domain)
        db.commit()
        return {"status": "merged", "merged_into": owner.firm_name, "canonical_website": domain}

    firm.canonical_website = domain
    firm.website_status = "resolved"
    firm.website_source = "human_confirmed"
    firm.website_confidence = 1.0
    firm.website_candidate = None
    db.commit()
    return {"status": "ok", "canonical_website": domain}


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

                    # Auto-assign: if search found a candidate but name-verification
                    # failed, trust the GPT result and promote it directly to
                    # canonical_website (no human review queue).
                    if result.review_candidate and not result.canonical_website:
                        domain = canonical_domain(result.review_candidate) or result.review_candidate
                        result = replace(
                            result,
                            canonical_website=domain,
                            website_status="resolved",
                            website_source="web_search",
                            review_candidate=None,
                        )

                    # Normalize bare domain on email-verified path too (safety).
                    if result.canonical_website:
                        normed = canonical_domain(result.canonical_website) or result.canonical_website
                        if normed != result.canonical_website:
                            result = replace(result, canonical_website=normed)

                    # Pre-check: if another firm already owns this canonical domain,
                    # auto-merge (new firm is the loser) instead of writing a
                    # conflicting canonical_website that would crash on flush.
                    if result.canonical_website:
                        owner = (
                            db.query(PifInfo)
                            .filter(
                                PifInfo.canonical_website == result.canonical_website,
                                PifInfo.id != firm.id,
                            )
                            .first()
                        )
                        if owner:
                            _auto_merge_domain_clash(db, winner=owner, loser=firm, domain=result.canonical_website)
                            db.commit()
                            return replace(result, website_status="merged")

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
