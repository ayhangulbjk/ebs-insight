"""
Pydantic schemas for control catalog contract validation.
Enforces AGENTS.md § 4 (Control Catalog Rules).
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
from enum import Enum


class IntentType(str, Enum):
    """Diagnostic domain intentions per AGENTS.md § 4.1"""
    CONC_MGR = "conc_mgr"
    WORKFLOW = "workflow"
    ADOP = "adop"
    INVALID_OBJECTS = "invalid_objects"
    DATA_INTEGRITY = "data_integrity"
    PERFORMANCE = "performance"


class SafetyClassification(str, Enum):
    """Safety classification per AGENTS.md § 4.3"""
    SAFE_READONLY = "SAFE_READONLY"
    SENSITIVE = "SENSITIVE"
    HIGH_RISK = "HIGH_RISK"


class KeywordSet(BaseModel):
    """Multilingual keywords (TR + EN)"""
    en: List[str] = Field(..., min_items=1, description="English keywords")
    tr: List[str] = Field(..., min_items=1, description="Turkish keywords")


class BindParameter(BaseModel):
    """Explicit bind parameter definition per AGENTS.md § 6.1"""
    name: str = Field(..., description="Bind parameter name (e.g., p_target_node)")
    type: Literal["VARCHAR2", "NUMBER", "DATE", "CLOB"] = Field(
        ..., description="Oracle data type"
    )
    optional: bool = Field(default=False, description="Is this parameter optional?")


class ResultColumn(BaseModel):
    """Expected result column schema"""
    name: str = Field(..., description="Column name")
    type: Literal["VARCHAR2", "NUMBER", "DATE", "CLOB"] = Field(
        ..., description="Oracle data type"
    )
    sensitive: bool = Field(
        default=False, description="Mark for redaction if sensitive"
    )


class QueryDefinition(BaseModel):
    """Single query definition per AGENTS.md § 4.1"""
    query_id: str = Field(..., description="Unique query identifier within control")
    sql_file: Optional[str] = Field(
        default=None, description="Path to SQL file (relative to knowledge/controls/)"
    )
    sql: Optional[str] = Field(default=None, description="Inline SQL (alternative to sql_file)")
    binds: List[BindParameter] = Field(
        default_factory=list, description="Bind parameters"
    )
    row_limit: int = Field(default=50, description="Max rows to fetch")
    timeout_seconds: int = Field(default=30, description="Query timeout")
    result_schema: List[ResultColumn] = Field(
        ..., description="Expected result columns"
    )

    @validator("sql_file", "sql", always=True)
    def sql_or_file_provided(cls, v, values):
        """Enforce: either sql or sql_file must be provided"""
        if "sql_file" in values and "sql" in values:
            sql_file = values.get("sql_file")
            sql = values.get("sql")
            if not sql_file and not sql:
                raise ValueError("Either 'sql_file' or 'sql' must be provided")
        return v


class ControlDefinition(BaseModel):
    """
    Complete control definition per AGENTS.md § 4.1 (Control Definition Contract).
    This is the SSOT (Single Source of Truth) for control catalog.
    """
    control_id: str = Field(
        ..., pattern="^[a-z_]+$", description="Stable unique control identifier"
    )
    version: str = Field(
        ..., description="Semantic version or date-based (e.g., 1.2 or 2026-01-29)"
    )
    title: str = Field(..., description="Control title (short)")
    description: str = Field(..., description="Detailed control description")
    intent: IntentType = Field(..., description="Diagnostic domain")
    keywords: KeywordSet = Field(..., description="Multilingual keywords (TR + EN)")
    queries: List[QueryDefinition] = Field(..., min_items=1, description="1..N queries")
    doc_hint: str = Field(
        ..., description="What to look for in results (interpretation guide)"
    )
    analysis_prompt: str = Field(
        ...,
        description="Instructions for LLM on how to interpret and summarize results",
    )
    knowledge_file: Optional[str] = Field(
        default=None,
        description="Optional markdown file with domain knowledge (e.g., 'invalid_objects.md')",
    )
    safety_classification: SafetyClassification = Field(
        default=SafetyClassification.SAFE_READONLY,
        description="Safety classification per AGENTS.md § 4.3",
    )


class ControlCatalog(BaseModel):
    """
    Top-level catalog containing all controls and metadata.
    """
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Catalog metadata (version, created_at, description)",
    )
    controls: List[ControlDefinition] = Field(..., min_items=1, description="All controls")

    @validator("controls")
    def unique_control_ids(cls, v):
        """Enforce: all control_id values must be unique"""
        ids = [c.control_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate control_id values detected")
        return v


# =======================
# Routing Decision Objects
# =======================


class CandidateScore(BaseModel):
    """Per-candidate score breakdown per AGENTS.md § 5.1"""
    control_id: str = Field(..., description="Control identifier")
    control_version: str = Field(..., description="Control version")
    keyword_match_score: float = Field(..., ge=0.0, le=1.0)
    intent_match_score: float = Field(..., ge=0.0, le=1.0)
    sql_shape_score: float = Field(default=0.0, ge=0.0, le=1.0)
    recency_boost: float = Field(default=0.0, ge=0.0, le=0.1)
    priority_boost: float = Field(default=0.0, ge=0.0, le=0.1)
    ambiguity_penalty: float = Field(default=0.0, ge=0.0, le=0.5)
    final_score: float = Field(..., ge=0.0, le=1.0, description="Computed final score")


class RouterDecision(BaseModel):
    """
    Router decision output per AGENTS.md § 5.1.
    MUST be explainable and logged.
    """
    request_id: str = Field(..., description="Unique request trace ID")
    prompt_intent: Literal["chit_chat", "ebs_control", "ambiguous", "unknown"] = Field(
        ..., description="Detected intent classification"
    )
    intent_confidence: float = Field(..., ge=0.0, le=1.0)
    candidates: List[CandidateScore] = Field(..., description="Top-N scored candidates")
    selected_control_id: Optional[str] = Field(
        default=None, description="Selected control ID (None if chit-chat or ambiguous)"
    )
    selected_control_version: Optional[str] = Field(
        default=None, description="Selected control version"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Final routing confidence (0-1)"
    )
    justification: str = Field(
        ..., description="Human-readable explanation of routing decision"
    )
    ambiguity_threshold_breach: bool = Field(
        default=False,
        description="True if confidence below threshold, ask for clarification",
    )
    suggested_interpretations: List[str] = Field(
        default_factory=list,
        description="Top 3 interpretations if ambiguous (per AGENTS.md § 5.3)",
    )


# =======================
# Query Execution Results
# =======================


class QueryExecutionResult(BaseModel):
    """Result of a single query execution"""
    query_id: str = Field(..., description="Query identifier")
    rows: List[Dict[str, Any]] = Field(..., description="Result rows (sanitized)")
    row_count: int = Field(..., description="Total rows returned")
    truncated: bool = Field(..., description="True if rows were capped/truncated")
    execution_time_ms: float = Field(..., description="Query execution time in ms")
    error: Optional[str] = Field(
        default=None, description="Error message if query failed"
    )


class ControlExecutionResult(BaseModel):
    """Result of executing all queries in a control"""
    control_id: str = Field(..., description="Control identifier")
    control_version: str = Field(..., description="Control version")
    intent: IntentType = Field(..., description="Control diagnostic intent")
    query_results: List[QueryExecutionResult] = Field(
        ..., description="Results from all queries"
    )
    total_execution_time_ms: float = Field(..., description="Total time for all queries")
    has_errors: bool = Field(..., description="True if any query failed")
    errors: List[str] = Field(
        default_factory=list, description="List of error messages from failed queries"
    )
    sanitized: bool = Field(
        default=True, description="True if sensitive data was redacted"
    )


# =======================
# LLM Interaction
# =======================


class LLMPromptContext(BaseModel):
    """Context passed to LLM for summarization"""
    control_title: str = Field(...)
    control_intent: IntentType = Field(...)
    doc_hint: str = Field(...)
    analysis_prompt: str = Field(...)
    query_results: ControlExecutionResult = Field(...)


class LLMOutputVerdictType(str, Enum):
    """Health/status verdict types"""
    OK = "OK"
    WARN = "WARN"
    CRIT = "CRIT"
    UNKNOWN = "UNKNOWN"


class LLMSummaryResponse(BaseModel):
    """Parsed LLM response per AGENTS.md § 7.3 (Output Contract)"""
    summary_bullets: List[str] = Field(
        ..., min_items=2, max_items=8, description="2-5 summary bullets (max 8 tolerated)"
    )
    verdict: LLMOutputVerdictType = Field(..., description="Health/status verdict")
    evidence: List[str] = Field(
        ..., description="Key metrics/rows referenced as evidence"
    )
    details: Optional[str] = Field(
        default=None, description="Optional, compact detail section"
    )
    next_checks: Optional[List[str]] = Field(
        default=None,
        description="Suggested next controls if confidence is low",
    )


# =======================
# Audit & Logging
# =======================


class AuditTrail(BaseModel):
    """Audit trail per AGENTS.md § 8.3 (Audit Trail)"""
    request_id: str = Field(..., description="Unique request ID")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    user_prompt: str = Field(..., description="Original user prompt (sanitized)")
    intent_classification: str = Field(...)
    intent_confidence: float = Field(...)
    router_decision_id: str = Field(..., description="Reference to router decision")
    selected_controls: List[str] = Field(..., description="List of [control_id:version]")
    db_queries_executed: int = Field(..., description="Number of DB queries")
    total_db_time_ms: float = Field(...)
    total_ollama_time_ms: float = Field(...)
    final_verdict: LLMOutputVerdictType = Field(...)
    result_rows_total: int = Field(...)
    result_truncated_markers: int = Field(..., description="Count of [TRUNCATED] marks")
    errors: List[str] = Field(default_factory=list, description="Error log entries")
