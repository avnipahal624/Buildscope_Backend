"""Request/response models for the API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=10)
    problem_statement: str = ""
    target_users: list[str] = []
    keywords: list[str] = []
    planned_features: list[str] = []


class ProjectOut(ORM):
    id: str
    name: str
    description: str
    problem_statement: str
    target_users: list
    keywords: list
    planned_features: list
    status: str
    created_at: datetime


class JobOut(ORM):
    id: str
    project_id: str
    kind: str
    status: str
    queries: list
    scope: dict
    usage: dict
    log: list
    error: Optional[str]
    model_version: str
    prompt_version: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class JobCreated(BaseModel):
    job_id: str
    status: str


class SimilarProjectOut(ORM):
    id: str
    run_id: str
    source_id: str
    name: str
    source_url: str
    description: Optional[str]
    problem_solved: Optional[str]
    target_users: list
    features: list
    technology: list
    limitations: list
    supporting_excerpt: Optional[str]
    excerpt_verified: bool
    similarity_score: float
    score_components: dict
    extraction_confidence: str
    collected_at: datetime


class ComparisonOut(ORM):
    id: str
    run_id: str
    similar_project_id: str
    shared_features: list
    differences: list
    possible_gaps: list
    explanation: str
    supporting_source_ids: list


class StakeholderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class StakeholderUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(suggested|confirmed|rejected)$")


class StakeholderOut(ORM):
    id: str
    project_id: str
    name: str
    description: str
    status: str
    created_by: str


class NeedOut(ORM):
    id: str
    stakeholder_id: str
    need_text: str
    need_type: str
    evidence_status: str
    supporting_count: int
    contradicting_count: int
    independent_source_count: int
    ai_interpretation: Optional[str]
    missing_information: list
    validation_question: Optional[str]


class EvidenceOut(ORM):
    id: str
    source_id: str
    claim_id: Optional[str]
    need_id: Optional[str]
    excerpt: str
    relation: str
    evidence_type: str
    excerpt_verified: bool
    retrieved_at: Optional[datetime]
    source_url: Optional[str] = None
    source_title: Optional[str] = None


class OpportunityOut(ORM):
    id: str
    origin: str
    description: str
    rationale: str
    linked_need_ids: list
    linked_project_ids: list
    status: str
