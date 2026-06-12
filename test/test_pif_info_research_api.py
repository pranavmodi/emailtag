import asyncio

import pytest
from fastapi import HTTPException

from app.api.api_v1.endpoints.pif_info import research_batch
from app.schemas.pif_info import ResearchBatchRequest


def test_research_batch_rejects_limit_over_25_before_db_access():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            research_batch(
                ResearchBatchRequest(
                    limit=26,
                    kinds=["research", "research_staff", "analyze_behavior"],
                ),
                db=None,
            )
        )

    assert exc_info.value.status_code == 400
    assert "limit must be <= 25" in exc_info.value.detail
