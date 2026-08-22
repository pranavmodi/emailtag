"""Authenticated endpoints for model-evaluation datasets."""

from typing import Any, List
from uuid import uuid4

import httpx
from loguru import logger

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.api_v1.dependencies import get_current_user
from app.db.session import AsyncSessionLocal, get_db
from app.models.user import User
from app.schemas.model_evaluation import (
    ClassificationBulkJobStartResponse,
    ClassificationBulkJobStatusResponse,
    ClassificationDatasetRequest,
    ClassificationRankingResponse,
    EvaluationModelCatalogResponse,
    EvaluationModelOption,
    EvaluationModelSettingUpdate,
    ModelEvaluationGroundTruthResponse,
    ModelEvaluationGroundTruthUpdate,
    ModelEvaluationJobStartResponse,
    ModelEvaluationJobStatusResponse,
    ModelEvaluationPilotResponse,
    ModelEvaluationRunRequest,
    ModelEvaluationRunResult,
    ModelEvaluationRunReviewUpdate,
    ModelEvaluationRunResponse,
    LegacyRxBulkJobStartResponse,
    LegacyRxBulkJobStatusResponse,
    LegacyRxCasesResponse,
    VisionBulkJobStartResponse,
    VisionBulkJobStatusResponse,
    VisionBulkRunRequest,
    VisionEvaluationResponse,
)
from app.services.classification_evaluation_service import get_classification_rankings
from app.services.model_evaluation_runner import (
    get_model_catalog,
    get_model_settings,
    get_case_ground_truth,
    list_model_evaluation_runs,
    review_model_evaluation_run,
    run_model_evaluation,
    save_model_setting,
    save_case_ground_truth,
    serialize_ground_truth,
    serialize_run,
)
from app.services.model_evaluation_service import build_model_evaluation_pilot
from app.services.vision_evaluation_service import (
    build_vision_evaluation,
    find_legacy_rx_cases,
    get_vision_document,
)

router = APIRouter()

# Manual evaluation calls can take several minutes when many hosted models are
# selected. Keep the HTTP requests short and let the detail page poll this
# process-local registry while the run continues in the API process.
_evaluation_jobs: dict[str, dict[str, Any]] = {}
_classification_bulk_jobs: dict[str, dict[str, Any]] = {}
_legacy_rx_bulk_jobs: dict[str, dict[str, Any]] = {}
_vision_bulk_jobs: dict[str, dict[str, Any]] = {}


def _evaluation_case_id(request: ModelEvaluationRunRequest) -> str:
    if request.case_type == "classification":
        if not request.conversation_id:
            raise ValueError("conversation_id is required for classification evaluations")
        return request.conversation_id
    if request.case_type == "vision":
        if not request.email_id or request.result_index is None:
            raise ValueError("email_id and result_index are required for vision evaluations")
        return f"{request.email_id}:{request.result_index}"
    raise ValueError("case_type must be classification or vision")


async def _execute_evaluation_job(
    job_id: str,
    request: ModelEvaluationRunRequest,
) -> None:
    job = _evaluation_jobs[job_id]
    job["status"] = "running"
    try:
        async with AsyncSessionLocal() as db:
            case_id, rows = await run_model_evaluation(db, request)
        job.update(
            status="completed",
            case_id=case_id,
            runs=[serialize_run(row) for row in rows],
            error=None,
        )
    except Exception as exc:  # pragma: no cover - defensive background boundary
        logger.exception("Model evaluation job {} failed", job_id)
        job.update(status="error", error=str(exc)[:2000], runs=[])


def _trim_evaluation_jobs(max_jobs: int = 100) -> None:
    while len(_evaluation_jobs) >= max_jobs:
        oldest_completed = next(
            (
                key
                for key, value in _evaluation_jobs.items()
                if value["status"] in {"completed", "error"}
            ),
            None,
        )
        if oldest_completed is None:
            return
        _evaluation_jobs.pop(oldest_completed, None)


def _trim_classification_bulk_jobs(max_jobs: int = 20) -> None:
    while len(_classification_bulk_jobs) >= max_jobs:
        oldest_completed = next(
            (
                key
                for key, value in _classification_bulk_jobs.items()
                if value["status"] in {"completed", "error"}
            ),
            None,
        )
        if oldest_completed is None:
            return
        _classification_bulk_jobs.pop(oldest_completed, None)


async def _active_model_keys(case_type: str) -> List[str]:
    async with AsyncSessionLocal() as db:
        enabled_by_key = await get_model_settings(db)
    return [
        model["key"]
        for model in get_model_catalog(case_type, enabled_by_key=enabled_by_key)
        if model["enabled"] and model["available"]
    ]


async def _execute_classification_bulk_job(
    job_id: str,
    conversation_ids: List[str],
    model_keys: List[str],
) -> None:
    job = _classification_bulk_jobs[job_id]
    job["status"] = "running"
    try:
        for conversation_id in conversation_ids:
            job["current_case_id"] = conversation_id
            try:
                async with AsyncSessionLocal() as db:
                    await run_model_evaluation(
                        db,
                        ModelEvaluationRunRequest(
                            case_type="classification",
                            conversation_id=conversation_id,
                            model_keys=model_keys,
                        ),
                    )
            except Exception as exc:  # Keep the remaining dataset running.
                logger.exception(
                    "Classification bulk job {} failed for {}", job_id, conversation_id
                )
                job["failed_cases"] += 1
                job["errors"].append(
                    {"case_id": conversation_id, "error": str(exc)[:500]}
                )
            finally:
                job["completed_cases"] += 1
        job.update(status="completed", current_case_id=None)
    except Exception as exc:  # pragma: no cover - defensive background boundary
        logger.exception("Classification bulk evaluation job {} failed", job_id)
        job.update(status="error", current_case_id=None, error=str(exc)[:2000])


def _trim_legacy_rx_bulk_jobs(max_jobs: int = 20) -> None:
    while len(_legacy_rx_bulk_jobs) >= max_jobs:
        oldest_completed = next(
            (
                key
                for key, value in _legacy_rx_bulk_jobs.items()
                if value["status"] in {"completed", "error"}
            ),
            None,
        )
        if oldest_completed is None:
            return
        _legacy_rx_bulk_jobs.pop(oldest_completed, None)


async def _execute_legacy_rx_bulk_job(
    job_id: str,
    cases: List[dict[str, Any]],
    model_keys: List[str],
) -> None:
    job = _legacy_rx_bulk_jobs[job_id]
    job["status"] = "running"
    try:
        for case in cases:
            job["current_case_id"] = case["case_id"]
            try:
                async with AsyncSessionLocal() as db:
                    await run_model_evaluation(
                        db,
                        ModelEvaluationRunRequest(
                            case_type="vision",
                            email_id=case["email_id"],
                            result_index=case["result_index"],
                            objective="rx",
                            model_keys=model_keys,
                        ),
                    )
            except Exception as exc:  # Keep the remaining RX cases running.
                logger.exception("Legacy RX bulk job {} failed for {}", job_id, case["case_id"])
                job["failed_cases"] += 1
                job["errors"].append(
                    {"case_id": case["case_id"], "error": str(exc)[:500]}
                )
            finally:
                job["completed_cases"] += 1
        job.update(status="completed", current_case_id=None)
    except Exception as exc:  # pragma: no cover - defensive background boundary
        logger.exception("Legacy RX bulk evaluation job {} failed", job_id)
        job.update(status="error", current_case_id=None, error=str(exc)[:2000])


def _trim_vision_bulk_jobs(max_jobs: int = 20) -> None:
    while len(_vision_bulk_jobs) >= max_jobs:
        oldest_completed = next(
            (
                key
                for key, value in _vision_bulk_jobs.items()
                if value["status"] in {"completed", "error"}
            ),
            None,
        )
        if oldest_completed is None:
            return
        _vision_bulk_jobs.pop(oldest_completed, None)


async def _execute_vision_bulk_job(
    job_id: str,
    objective: str,
    cases: List[dict[str, Any]],
    model_keys: List[str],
) -> None:
    job = _vision_bulk_jobs[job_id]
    job["status"] = "running"
    try:
        for case in cases:
            case_id = f'{case["email_id"]}:{case["result_index"]}'
            job["current_case_id"] = case_id
            try:
                async with AsyncSessionLocal() as db:
                    await run_model_evaluation(
                        db,
                        ModelEvaluationRunRequest(
                            case_type="vision",
                            email_id=case["email_id"],
                            result_index=case["result_index"],
                            objective=objective,
                            model_keys=model_keys,
                        ),
                    )
            except Exception as exc:  # Keep the remaining documents running.
                logger.exception("Vision bulk job {} failed for {}", job_id, case_id)
                job["failed_cases"] += 1
                job["errors"].append({"case_id": case_id, "error": str(exc)[:500]})
            finally:
                job["completed_cases"] += 1
        job.update(status="completed", current_case_id=None)
    except Exception as exc:  # pragma: no cover - defensive background boundary
        logger.exception("Vision bulk evaluation job {} failed", job_id)
        job.update(status="error", current_case_id=None, error=str(exc)[:2000])


@router.get("/models", response_model=EvaluationModelCatalogResponse)
async def get_evaluation_models(
    case_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EvaluationModelCatalogResponse:
    """List models available to the manual evaluation runner."""
    try:
        enabled_by_key = await get_model_settings(db)
        return EvaluationModelCatalogResponse(
            models=get_model_catalog(case_type, enabled_by_key=enabled_by_key)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/models/settings", response_model=EvaluationModelOption)
async def put_evaluation_model_setting(
    payload: EvaluationModelSettingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EvaluationModelOption:
    """Enable or disable a model only in the manual evaluation runner."""
    try:
        await save_model_setting(
            db,
            model_key=payload.model_key,
            enabled=payload.enabled,
            updated_by=user.username,
        )
        option = next(
            item
            for item in get_model_catalog(enabled_by_key={payload.model_key: payload.enabled})
            if item["key"] == payload.model_key
        )
        return EvaluationModelOption(**option)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/runs", response_model=ModelEvaluationRunResponse)
async def get_evaluation_runs(
    case_type: str = Query(...),
    case_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ModelEvaluationRunResponse:
    """Load previously persisted manual results for one case."""
    try:
        rows = await list_model_evaluation_runs(db, case_type=case_type, case_id=case_id)
        return ModelEvaluationRunResponse(
            case_id=case_id,
            runs=[serialize_run(row) for row in rows],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/runs", response_model=ModelEvaluationRunResponse)
async def create_evaluation_runs(
    request: ModelEvaluationRunRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ModelEvaluationRunResponse:
    """Manually run selected models without changing production case state."""
    try:
        case_id, rows = await run_model_evaluation(db, request)
        return ModelEvaluationRunResponse(
            case_id=case_id,
            runs=[serialize_run(row) for row in rows],
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/runs/start",
    response_model=ModelEvaluationJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_evaluation_runs(
    request: ModelEvaluationRunRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
) -> ModelEvaluationJobStartResponse:
    """Start a long manual evaluation without holding the proxy request open."""
    try:
        case_id = _evaluation_case_id(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _trim_evaluation_jobs()
    job_id = str(uuid4())
    _evaluation_jobs[job_id] = {
        "job_id": job_id,
        "case_id": case_id,
        "status": "queued",
        "runs": [],
        "error": None,
    }
    background_tasks.add_task(_execute_evaluation_job, job_id, request.model_copy(deep=True))
    return ModelEvaluationJobStartResponse(job_id=job_id, case_id=case_id, status="queued")


@router.get("/runs/jobs/{job_id}", response_model=ModelEvaluationJobStatusResponse)
async def get_evaluation_job(
    job_id: str,
    _: User = Depends(get_current_user),
) -> ModelEvaluationJobStatusResponse:
    """Return the current state of a background manual evaluation."""
    job = _evaluation_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation job was not found or the API was restarted",
        )
    return ModelEvaluationJobStatusResponse(**job)


@router.post(
    "/classification/bulk/start",
    response_model=ClassificationBulkJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_classification_bulk_evaluation(
    payload: ClassificationDatasetRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
) -> ClassificationBulkJobStartResponse:
    """Run every enabled classification model over the supplied evaluation dataset."""
    active_job = next(
        (
            job
            for job in reversed(list(_classification_bulk_jobs.values()))
            if job["status"] in {"queued", "running"}
        ),
        None,
    )
    if active_job:
        return ClassificationBulkJobStartResponse(
            job_id=active_job["job_id"],
            status=active_job["status"],
            total_cases=active_job["total_cases"],
            total_models=active_job["total_models"],
        )
    conversation_ids = list(dict.fromkeys(payload.conversation_ids))
    model_keys = await _active_model_keys("classification")
    if not model_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No enabled classification models are available",
        )
    _trim_classification_bulk_jobs()
    job_id = str(uuid4())
    _classification_bulk_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "total_cases": len(conversation_ids),
        "completed_cases": 0,
        "failed_cases": 0,
        "total_models": len(model_keys),
        "current_case_id": None,
        "errors": [],
        "error": None,
    }
    background_tasks.add_task(
        _execute_classification_bulk_job,
        job_id,
        conversation_ids,
        model_keys,
    )
    return ClassificationBulkJobStartResponse(
        job_id=job_id,
        status="queued",
        total_cases=len(conversation_ids),
        total_models=len(model_keys),
    )


@router.get(
    "/classification/bulk/active",
    response_model=ClassificationBulkJobStatusResponse | None,
)
async def get_active_classification_bulk_job(
    _: User = Depends(get_current_user),
) -> ClassificationBulkJobStatusResponse | None:
    job = next(
        (
            item
            for item in reversed(list(_classification_bulk_jobs.values()))
            if item["status"] in {"queued", "running"}
        ),
        None,
    )
    return ClassificationBulkJobStatusResponse(**job) if job else None


@router.get(
    "/classification/bulk/jobs/{job_id}",
    response_model=ClassificationBulkJobStatusResponse,
)
async def get_classification_bulk_job(
    job_id: str,
    _: User = Depends(get_current_user),
) -> ClassificationBulkJobStatusResponse:
    job = _classification_bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classification evaluation job was not found or the API was restarted",
        )
    return ClassificationBulkJobStatusResponse(**job)


@router.post(
    "/classification/rankings",
    response_model=ClassificationRankingResponse,
)
async def get_dataset_classification_rankings(
    payload: ClassificationDatasetRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ClassificationRankingResponse:
    enabled_by_key = await get_model_settings(db)
    active_model_keys = {
        model["key"]
        for model in get_model_catalog("classification", enabled_by_key=enabled_by_key)
        if model["enabled"] and model["available"]
    }
    ranking = await get_classification_rankings(
        db,
        payload.conversation_ids,
        active_model_keys,
    )
    return ClassificationRankingResponse(**ranking)


@router.post(
    "/vision/bulk/start",
    response_model=VisionBulkJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_vision_bulk_evaluation(
    payload: VisionBulkRunRequest,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
) -> VisionBulkJobStartResponse:
    """Run every enabled vision model over the supplied RX or lien cases."""
    if payload.objective not in {"rx", "lien"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vision objective must be rx or lien",
        )
    active_job = next(
        (
            job
            for job in reversed(list(_vision_bulk_jobs.values()))
            if job["objective"] == payload.objective
            and job["status"] in {"queued", "running"}
        ),
        None,
    )
    if active_job:
        return VisionBulkJobStartResponse(**active_job)

    model_keys = await _active_model_keys("vision")
    if not model_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No enabled vision models are available",
        )
    cases = list(
        {
            (case.email_id, case.result_index): case.model_dump()
            for case in payload.cases
        }.values()
    )
    _trim_vision_bulk_jobs()
    job_id = str(uuid4())
    _vision_bulk_jobs[job_id] = {
        "job_id": job_id,
        "objective": payload.objective,
        "status": "queued",
        "total_cases": len(cases),
        "completed_cases": 0,
        "failed_cases": 0,
        "total_models": len(model_keys),
        "current_case_id": None,
        "errors": [],
        "error": None,
    }
    background_tasks.add_task(
        _execute_vision_bulk_job,
        job_id,
        payload.objective,
        cases,
        model_keys,
    )
    return VisionBulkJobStartResponse(
        job_id=job_id,
        objective=payload.objective,
        status="queued",
        total_cases=len(cases),
        total_models=len(model_keys),
    )


@router.get(
    "/vision/bulk/jobs/{job_id}",
    response_model=VisionBulkJobStatusResponse,
)
async def get_vision_bulk_evaluation_job(
    job_id: str,
    _: User = Depends(get_current_user),
) -> VisionBulkJobStatusResponse:
    job = _vision_bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vision evaluation job was not found or the API was restarted",
        )
    return VisionBulkJobStatusResponse(**job)


@router.get("/vision/rx/legacy", response_model=LegacyRxCasesResponse)
async def get_legacy_rx_evaluation_cases(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LegacyRxCasesResponse:
    enabled_by_key = await get_model_settings(db)
    active_model_keys = {
        model["key"]
        for model in get_model_catalog("vision", enabled_by_key=enabled_by_key)
        if model["enabled"] and model["available"]
    }
    cases = await find_legacy_rx_cases(db, active_model_keys)
    return LegacyRxCasesResponse(total_cases=len(cases), cases=cases)


@router.post(
    "/vision/rx/legacy/rerun/start",
    response_model=LegacyRxBulkJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_legacy_rx_bulk_rerun(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LegacyRxBulkJobStartResponse:
    enabled_by_key = await get_model_settings(db)
    active_models = [
        model
        for model in get_model_catalog("vision", enabled_by_key=enabled_by_key)
        if model["enabled"] and model["available"]
    ]
    model_keys = [model["key"] for model in active_models]
    cases = await find_legacy_rx_cases(db, set(model_keys))
    if not cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active-model RX results require a schema rerun",
        )
    _trim_legacy_rx_bulk_jobs()
    job_id = str(uuid4())
    _legacy_rx_bulk_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "total_cases": len(cases),
        "completed_cases": 0,
        "failed_cases": 0,
        "total_models": len(model_keys),
        "current_case_id": None,
        "errors": [],
        "error": None,
    }
    background_tasks.add_task(
        _execute_legacy_rx_bulk_job,
        job_id,
        cases,
        model_keys,
    )
    return LegacyRxBulkJobStartResponse(
        job_id=job_id,
        status="queued",
        total_cases=len(cases),
        total_models=len(model_keys),
    )


@router.get(
    "/vision/rx/legacy/rerun/jobs/{job_id}",
    response_model=LegacyRxBulkJobStatusResponse,
)
async def get_legacy_rx_bulk_rerun_job(
    job_id: str,
    _: User = Depends(get_current_user),
) -> LegacyRxBulkJobStatusResponse:
    job = _legacy_rx_bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legacy RX rerun job was not found or the API was restarted",
        )
    return LegacyRxBulkJobStatusResponse(**job)


@router.get("/ground-truth", response_model=ModelEvaluationGroundTruthResponse)
async def get_evaluation_ground_truth(
    case_type: str = Query(...),
    case_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ModelEvaluationGroundTruthResponse:
    """Load the human-reviewed reference answer for one evaluation case."""
    try:
        review = await get_case_ground_truth(db, case_type=case_type, case_id=case_id)
        return ModelEvaluationGroundTruthResponse(
            **serialize_ground_truth(review, case_type=case_type, case_id=case_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/ground-truth", response_model=ModelEvaluationGroundTruthResponse)
async def put_evaluation_ground_truth(
    payload: ModelEvaluationGroundTruthUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelEvaluationGroundTruthResponse:
    """Save a reference answer used only for evaluation scoring."""
    try:
        review = await save_case_ground_truth(
            db,
            case_type=payload.case_type,
            case_id=payload.case_id,
            reference_output=payload.reference_output,
            reference_text=payload.reference_text,
            notes=payload.notes,
            reference_source=payload.reference_source,
            seed_model_key=payload.seed_model_key,
            seed_run_id=payload.seed_run_id,
            reviewed_by=user.username,
        )
        return ModelEvaluationGroundTruthResponse(
            **serialize_ground_truth(
                review, case_type=payload.case_type, case_id=payload.case_id
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/runs/{run_id}/review", response_model=ModelEvaluationRunResult)
async def patch_evaluation_run_review(
    run_id: str,
    payload: ModelEvaluationRunReviewUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelEvaluationRunResult:
    """Record a human verdict and preferred result without changing production state."""
    try:
        row = await review_model_evaluation_run(
            db,
            run_id=run_id,
            human_rating=payload.human_rating,
            human_notes=payload.human_notes,
            is_preferred=payload.is_preferred,
            reviewed_by=user.username,
        )
        return ModelEvaluationRunResult(**serialize_run(row))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/pilot",
    response_model=ModelEvaluationPilotResponse,
    summary="Load a read-only model-evaluation pilot",
)
async def get_model_evaluation_pilot(
    examples_per_tag: int = Query(5, ge=1, le=5),
    single_message_only: bool = Query(True),
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ModelEvaluationPilotResponse:
    """Load up to five single-message examples per configured classifier tag."""
    try:
        payload = await build_model_evaluation_pilot(
            db,
            examples_per_tag=examples_per_tag,
            single_message_only=single_message_only,
            refresh=refresh,
        )
        return ModelEvaluationPilotResponse(**payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to load model-evaluation pilot: {exc}",
        ) from exc


@router.get("/vision", response_model=VisionEvaluationResponse)
async def get_vision_evaluation(
    examples_per_objective: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> VisionEvaluationResponse:
    """Load OCR, RX, and lien examples from existing processed documents."""
    enabled_by_key = await get_model_settings(db)
    active_model_keys = {
        model["key"]
        for model in get_model_catalog("vision", enabled_by_key=enabled_by_key)
        if model["enabled"] and model["available"]
    }
    payload = await build_vision_evaluation(
        db,
        examples_per_objective=examples_per_objective,
        allowed_model_keys=active_model_keys,
    )
    return VisionEvaluationResponse(**payload)


@router.get("/vision/{email_id}/{result_index}/content")
async def view_vision_evaluation_document(
    email_id: str,
    result_index: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Response:
    """Proxy a selected Front attachment without exposing credentials or source URLs."""
    try:
        content, content_type, filename = await get_vision_document(
            db,
            email_id=email_id,
            result_index=result_index,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to retrieve the document from Front",
        ) from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )
