from pydantic import BaseModel, Field


class LiveState(BaseModel):
    current_stage: str = "产品讲解期"
    elapsed_seconds: int = 0
    planned_seconds: int = 3600
    current_sku: str = ""


class StageDirective(BaseModel):
    """Operator-issued structured instruction, e.g. jump into the promotion stage."""

    target_stage: str
    reason: str = ""


class CommentAnalysis(BaseModel):
    hot_words: dict[str, int] = Field(default_factory=dict)
    negative_feedback: list[str] = Field(default_factory=list)
    purchase_intent: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    repeated_questions: dict[str, int] = Field(default_factory=dict)
    repeated_comments: dict[str, int] = Field(default_factory=dict)


class InteractionResult(BaseModel):
    comment_analysis: CommentAnalysis
    summary: list[str] = Field(default_factory=list)
    mode: str = "rules"


class ProductSellingPoint(BaseModel):
    topic: str
    label: str
    description: str
    match_keywords: list[str] = Field(default_factory=list)
    evidence: str = ""
    verified: bool = False


class Product(BaseModel):
    sku_id: str
    name: str
    specification: str = ""
    price: float | None = None
    ingredients: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    selling_points: list[ProductSellingPoint] = Field(default_factory=list)
    usage_instructions: list[str] = Field(default_factory=list)
    applicable_audience: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)


class BackendMetrics(BaseModel):
    online_count: int = 0
    cart_click_rate_change: str = ""
    conversion_rate: str = ""


class AgentInput(BaseModel):
    live_state: LiveState
    directive: StageDirective | None = None
    recent_comments: list[str] = Field(default_factory=list)
    comment_analysis: CommentAnalysis = Field(default_factory=CommentAnalysis)
    event_counts: dict[str, int] = Field(default_factory=dict)
    product: Product
    backend_metrics: BackendMetrics = Field(default_factory=BackendMetrics)


class LiveEvent(BaseModel):
    kind: str
    room_id: int
    timestamp: int
    text: str = ""
    user: str = ""
    metrics: dict[str, int | float | str] = Field(default_factory=dict)


class LiveStartRequest(BaseModel):
    source: str = "bilibili"
    elapsed_seconds: int | None = Field(default=None, ge=0)
    planned_seconds: int | None = Field(default=None, ge=1)
    current_stage: str | None = None
    target_stage: str | None = None
    product: Product | None = None
    backend_metrics: BackendMetrics | None = None
    window_seconds: int | None = Field(default=None, ge=3, le=120)
    auto_analyze: bool = False


class LiveConfigUpdate(BaseModel):
    """Runtime overrides for an already-listening session."""

    product: Product | None = None
    elapsed_seconds: int | None = Field(default=None, ge=0)
    planned_seconds: int | None = Field(default=None, ge=1)
    current_stage: str | None = None
    target_stage: str | None = None
    auto_analyze: bool | None = None


class LiveMetricsUpdate(BaseModel):
    online_count: int | None = Field(default=None, ge=0)
    cart_click_rate_change: str | None = None
    conversion_rate: str | None = None
    source: str = "external"


class Suggestion(BaseModel):
    priority: str
    score: float
    suggested_script: str
    recommended_action: str
    trigger_reason: str
    compliance_status: str
    topic: str = ""
    intent: str = ""
    compliance_replacements: list[str] = Field(default_factory=list)


class StageState(BaseModel):
    current_stage: str
    declared_stage: str = ""
    stage_focus: str = ""
    stage_goal: str = ""
    next_stage: str | None = None
    next_stage_preparation: list[str] = Field(default_factory=list)
    stage_progress: float = 0.0
    stage_remaining_seconds: int = 0
    total_remaining_seconds: int = 0
    source: str = "clock"
    notes: list[str] = Field(default_factory=list)


class AgentOutput(BaseModel):
    suggestions: list[Suggestion]
    analysis_summary: list[str] = Field(default_factory=list)
    stage_state: StageState | None = None
    decision_notes: list[str] = Field(default_factory=list)
    generation_mode: str = "rules"
    interaction_mode: str = "rules"
    ai_decision_summary: str = ""
