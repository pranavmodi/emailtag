"""Schemas for the model-evaluation dataset pilot."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.conversation_replay import ConversationReplayMessage


class ModelEvaluationClassification(BaseModel):
    """A classification decision captured by EmailTag."""

    step_name: str
    step_order: int
    classification_path: Optional[str] = None
    chosen_option: Optional[str] = None
    classification_reason: Optional[str] = None
    llm_model: Optional[str] = None
    total_tokens: Optional[int] = None
    created_at: Optional[datetime] = None


class ModelEvaluationAction(BaseModel):
    """A user-visible action derived from Front or EmailTag history."""

    action_type: str
    label: str
    source: str
    timestamp: Optional[datetime] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ModelEvaluationGroundTruth(BaseModel):
    """Review state for the benchmark label."""

    status: str = "unreviewed"
    reviewed_tags: List[str] = Field(default_factory=list)
    reviewed_actions: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ModelEvaluationConversation(BaseModel):
    """One Front conversation joined with EmailTag processing history."""

    conversation_id: str
    sample_tags: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    front_url: str
    created_at: Optional[datetime] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    current_tags: List[str] = Field(default_factory=list)
    stored_tags: List[str] = Field(default_factory=list)
    emailtag_statuses: List[str] = Field(default_factory=list)
    messages: List[ConversationReplayMessage] = Field(default_factory=list)
    classifications: List[ModelEvaluationClassification] = Field(default_factory=list)
    actions: List[ModelEvaluationAction] = Field(default_factory=list)
    email_record_count: int = 0
    outbound_reply_count: int = 0
    attachment_count: int = 0
    ocr_result_count: int = 0
    ground_truth: ModelEvaluationGroundTruth = Field(
        default_factory=ModelEvaluationGroundTruth
    )
    load_error: Optional[str] = None


class ModelEvaluationTagCoverage(BaseModel):
    """Coverage achieved for one configured classification output tag."""

    tag_name: str
    requested: int
    found: int
    missing: int


class ModelEvaluationPilotResponse(BaseModel):
    """Response for the read-only classification benchmark dataset."""

    source_population: str
    selection_criteria: str
    candidates_scanned: int
    examples_per_tag: int
    configured_tag_count: int
    requested_example_count: int
    tag_coverage: List[ModelEvaluationTagCoverage]
    conversation_count: int
    loaded_count: int
    failed_count: int
    generated_at: datetime
    conversations: List[ModelEvaluationConversation]


class VisionEvaluationExample(BaseModel):
    """One document selected for a vision benchmark objective."""

    example_id: str
    email_id: str
    conversation_id: str
    objective: str
    filename: str
    content_type: Optional[str] = None
    document_type: str
    created_at: Optional[datetime] = None
    page_count: int = 0
    has_extracted_text: bool = False
    current_output: Dict[str, Any] = Field(default_factory=dict)
    preview_url: str
    ground_truth_status: str = "unreviewed"
    evaluation_summary: Dict[str, Any] = Field(default_factory=dict)


class VisionEvaluationObjectiveCoverage(BaseModel):
    objective: str
    requested: int
    found: int
    description: str
    metrics: List[str]


class VisionEvaluationResponse(BaseModel):
    examples_per_objective: int
    generated_at: datetime
    coverage: List[VisionEvaluationObjectiveCoverage]
    examples: List[VisionEvaluationExample]
    rankings: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)


class EvaluationModelOption(BaseModel):
    key: str
    provider: str
    model: str
    display_name: str
    case_types: List[str]
    input_price_per_million: float
    output_price_per_million: float
    available: bool
    enabled: bool = True
    availability_note: Optional[str] = None


class EvaluationModelCatalogResponse(BaseModel):
    models: List[EvaluationModelOption]


class EvaluationModelSettingUpdate(BaseModel):
    model_key: str
    enabled: bool


class ModelEvaluationRunRequest(BaseModel):
    case_type: str
    model_keys: List[str] = Field(min_length=1)
    conversation_id: Optional[str] = None
    email_id: Optional[str] = None
    result_index: Optional[int] = Field(default=None, ge=0)
    objective: Optional[str] = None


class ModelEvaluationRunResult(BaseModel):
    id: str
    case_type: str
    case_id: str
    conversation_id: Optional[str] = None
    email_id: Optional[str] = None
    result_index: Optional[int] = None
    objective: Optional[str] = None
    provider: str
    model: str
    model_key: str
    status: str
    output: Optional[Dict[str, Any]] = None
    raw_usage: Optional[Dict[str, Any]] = None
    request_metadata: Optional[Dict[str, Any]] = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0
    error_text: Optional[str] = None
    human_rating: Optional[str] = None
    human_notes: Optional[str] = None
    is_preferred: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ModelEvaluationRunResponse(BaseModel):
    case_id: str
    runs: List[ModelEvaluationRunResult]


class ModelEvaluationJobStartResponse(BaseModel):
    job_id: str
    case_id: str
    status: str = "queued"


class ModelEvaluationJobStatusResponse(BaseModel):
    job_id: str
    case_id: str
    status: str
    runs: List[ModelEvaluationRunResult] = Field(default_factory=list)
    error: Optional[str] = None


class ClassificationDatasetRequest(BaseModel):
    conversation_ids: List[str] = Field(min_length=1, max_length=500)


class ClassificationBulkJobStartResponse(BaseModel):
    job_id: str
    status: str = "queued"
    total_cases: int
    total_models: int


class ClassificationBulkJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_cases: int
    completed_cases: int = 0
    failed_cases: int = 0
    total_models: int
    current_case_id: Optional[str] = None
    errors: List[Dict[str, str]] = Field(default_factory=list)
    error: Optional[str] = None


class VisionBulkCase(BaseModel):
    email_id: str
    result_index: int = Field(ge=0)


class VisionBulkRunRequest(BaseModel):
    objective: str
    cases: List[VisionBulkCase] = Field(min_length=1, max_length=50)


class VisionBulkJobStartResponse(BaseModel):
    job_id: str
    objective: str
    status: str = "queued"
    total_cases: int
    total_models: int


class VisionBulkJobStatusResponse(BaseModel):
    job_id: str
    objective: str
    status: str
    total_cases: int
    completed_cases: int = 0
    failed_cases: int = 0
    total_models: int
    current_case_id: Optional[str] = None
    errors: List[Dict[str, str]] = Field(default_factory=list)
    error: Optional[str] = None


class ClassificationModelRanking(BaseModel):
    model_key: str
    provider: str
    model: str
    attempted_cases: int
    completed_cases: int
    scored_cases: int
    exact_matches: int
    classification_mismatches: int = 0
    execution_errors: int = 0
    final_tag_matches: int
    accuracy: Optional[float] = None
    final_tag_accuracy: Optional[float] = None
    average_cost_usd: Optional[float] = None
    total_cost_usd: float = 0
    average_tokens: int = 0
    completion_rate: float = 0
    tag_accuracy: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ClassificationRankingResponse(BaseModel):
    shortlisted_cases: int
    reference_cases: int
    rankings: List[ClassificationModelRanking] = Field(default_factory=list)


class LegacyRxCase(BaseModel):
    case_id: str
    email_id: str
    result_index: int
    legacy_model_keys: List[str] = Field(default_factory=list)


class LegacyRxCasesResponse(BaseModel):
    total_cases: int
    cases: List[LegacyRxCase] = Field(default_factory=list)


class LegacyRxBulkJobStartResponse(BaseModel):
    job_id: str
    status: str = "queued"
    total_cases: int
    total_models: int


class LegacyRxBulkJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_cases: int
    completed_cases: int = 0
    failed_cases: int = 0
    total_models: int
    current_case_id: Optional[str] = None
    errors: List[Dict[str, str]] = Field(default_factory=list)
    error: Optional[str] = None


class ModelEvaluationGroundTruthUpdate(BaseModel):
    case_type: str
    case_id: str
    reference_output: Optional[Dict[str, Any]] = None
    reference_text: Optional[str] = None
    notes: Optional[str] = None
    reference_source: str = "human"
    seed_model_key: Optional[str] = None
    seed_run_id: Optional[str] = None


class ModelEvaluationGroundTruthResponse(BaseModel):
    case_type: str
    case_id: str
    reference_output: Optional[Dict[str, Any]] = None
    reference_text: Optional[str] = None
    notes: Optional[str] = None
    reference_source: str = "unknown"
    seed_model_key: Optional[str] = None
    seed_run_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class ModelEvaluationRunReviewUpdate(BaseModel):
    human_rating: Optional[str] = None
    human_notes: Optional[str] = None
    is_preferred: bool = False
