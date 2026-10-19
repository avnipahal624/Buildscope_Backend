"""Database tables for Modules 2 and 3 (+ minimal stubs for Modules 1 and 7).

Design rules:
* Source facts (sources, evidence.excerpt) are stored separately from AI output
  (ai_interpretation, comparisons, ...).
* Every AI-generated row records model_version / prompt_version where useful.
* IDs are string UUIDs so other modules can reference them stably.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ----------------------------------------------------------------- Module 1 stub
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    problem_statement: Mapped[str] = mapped_column(Text, default="")
    target_users: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    planned_features: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------------------------------------------- Jobs / runs
class ResearchRun(Base):
    """One background job. kind = 'research' or 'stakeholders'."""
    __tablename__ = "research_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    # pending | running | completed | completed_with_errors | failed
    status: Mapped[str] = mapped_column(String(30), default="pending")
    queries: Mapped[list] = mapped_column(JSON, default=list)
    scope: Mapped[dict] = mapped_column(JSON, default=dict)   # stage, counts, coverage note
    usage: Mapped[dict] = mapped_column(JSON, default=dict)   # token / call counters
    log: Mapped[list] = mapped_column(JSON, default=list)     # warnings and errors
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ------------------------------------------- Module 7 stubs: sources/claims/evidence
class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    url: Mapped[str] = mapped_column(Text)
    url_normalized: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="website")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # cleaned page text (cache)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(20), default="pending")  # ok | failed
    fetch_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    claim_type: Mapped[str] = mapped_column(String(30))  # stakeholder_need | project_description
    text: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(10), default="ai")  # ai | user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("research_runs.id"), nullable=True, index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(ForeignKey("claims.id"), nullable=True, index=True)
    need_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    excerpt: Mapped[str] = mapped_column(Text)               # verbatim, never edited
    relation: Mapped[str] = mapped_column(String(15), default="supports")  # supports | contradicts
    evidence_type: Mapped[str] = mapped_column(String(20), default="website")
    excerpt_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ------------------------------------------------------------------- Module 2
class SimilarProject(Base):
    __tablename__ = "similar_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    name: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # None = unknown
    problem_solved: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_users: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[list] = mapped_column(JSON, default=list)
    technology: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    supporting_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    excerpt_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_components: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_confidence: Mapped[str] = mapped_column(String(10), default="low")
    model_version: Mapped[str] = mapped_column(String(100), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectComparison(Base):
    __tablename__ = "project_comparisons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    similar_project_id: Mapped[str] = mapped_column(ForeignKey("similar_projects.id"))
    shared_features: Mapped[list] = mapped_column(JSON, default=list)
    differences: Mapped[list] = mapped_column(JSON, default=list)
    possible_gaps: Mapped[list] = mapped_column(JSON, default=list)   # hypotheses only
    explanation: Mapped[str] = mapped_column(Text, default="")
    supporting_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(100), default="")


# ------------------------------------------------------------------- Module 3
class Stakeholder(Base):
    __tablename__ = "stakeholders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(15), default="suggested")  # suggested|confirmed|rejected
    created_by: Mapped[str] = mapped_column(String(10), default="ai")


class StakeholderNeed(Base):
    __tablename__ = "stakeholder_needs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    stakeholder_id: Mapped[str] = mapped_column(ForeignKey("stakeholders.id"), index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(ForeignKey("claims.id"), nullable=True)
    need_text: Mapped[str] = mapped_column(Text)
    # explicit | pattern | hypothesis  (computed in code from the evidence)
    need_type: Mapped[str] = mapped_column(String(15), default="hypothesis")
    # unverified | supported | strongly_supported | conflicting | needs_further_research
    evidence_status: Mapped[str] = mapped_column(String(25), default="unverified")
    supporting_count: Mapped[int] = mapped_column(Integer, default=0)
    contradicting_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0)
    # ---- AI output, always kept apart from the quotes in `evidence` ----
    ai_interpretation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    missing_information: Mapped[list] = mapped_column(JSON, default=list)
    validation_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")


class NeedSolutionLink(Base):
    """Bridge to Module 4: which existing features/limitations relate to a need."""
    __tablename__ = "need_solution_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    need_id: Mapped[str] = mapped_column(ForeignKey("stakeholder_needs.id"), index=True)
    similar_project_id: Mapped[str] = mapped_column(ForeignKey("similar_projects.id"), index=True)
    relation: Mapped[str] = mapped_column(String(25))   # related_feature | related_limitation
    text: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id"), index=True)
    origin: Mapped[str] = mapped_column(String(20))   # research_gap | unmet_need
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    linked_need_ids: Mapped[list] = mapped_column(JSON, default=list)
    linked_project_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(15), default="hypothesis")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# ------------------------------------------------------------------- Module 5/6
class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    acceptance_test: Mapped[str] = mapped_column(Text, default="")  # how to check it
    status: Mapped[str] = mapped_column(String(15), default="proposed")
    created_by: Mapped[str] = mapped_column(String(10), default="ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VerificationResult(Base):
    __tablename__ = "verification_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"), index=True)
    test_name: Mapped[str] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(10))   # pass | fail | error
    details: Mapped[str] = mapped_column(Text, default="")
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# ------------------------------------------------------------------- Project requirements (step 1)
class ProjectRequirement(Base):
    __tablename__ = "project_requirements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    requirement_type: Mapped[str] = mapped_column(String(50), default="functional")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
