from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str
    name: str
    category: str
    description: str = ''
    team_size_min: Optional[int] = None
    team_size_max: Optional[int] = None
    integrations: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    deployment: List[str] = Field(default_factory=list)
    pricing_tier: str = ''
    website: str = ''
    source_row: Optional[int] = None
    extra_fields: Dict[str, Any] = Field(default_factory=dict)


class DataIssue(BaseModel):
    row: int
    field: Optional[str] = None
    issue: str
    severity: str = 'warning'
    original: Optional[str] = None
    normalized: Optional[str] = None


class DataQualityReport(BaseModel):
    rows_received: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    duplicates_removed: int = 0
    repair_counts: Dict[str, int] = Field(default_factory=dict)
    missing_counts: Dict[str, int] = Field(default_factory=dict)
    issues: List[DataIssue] = Field(default_factory=list)
    score: float = 0.0


class CatalogIngestResponse(BaseModel):
    report: DataQualityReport
    products: int


class ProbeQuestion(BaseModel):
    id: str
    field: str
    question: str
    why_it_matters: str
    options: List[str] = Field(default_factory=list)
    expected_impact: float = 0.0


class CustomerNeeds(BaseModel):
    raw_query: str
    category: Optional[str] = None
    team_size: Optional[int] = None
    integrations: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    deployment: List[str] = Field(default_factory=list)
    pricing_tier: Optional[str] = None
    budget_text: Optional[str] = None
    must_haves: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    excluded_integrations: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    extraction_notes: List[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    field: str
    status: str
    requirement: str
    evidence: str
    contribution: float
    source_row: Optional[int] = None


class Recommendation(BaseModel):
    rank: int
    product: Product
    score: float
    match_summary: str
    why_recommended: List[str]
    improve_fit: List[str]
    matched_requirements: List[str]
    unmet_requirements: List[str]
    evidence: List[EvidenceItem] = Field(default_factory=list)
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    hard_constraints_satisfied: bool = True


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)
    answers: Dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=3, ge=1, le=3)


class QueryResponse(BaseModel):
    status: str
    needs: CustomerNeeds
    probes: List[ProbeQuestion] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    trace: Dict[str, Any] = Field(default_factory=dict)
