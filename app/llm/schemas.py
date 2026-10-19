"""Schemas the LLM must fill in. Optional/None always means 'unknown', never a guess."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class QueryList(BaseModel):
    queries: list[str] = Field(default_factory=list)


class ExtractedProject(BaseModel):
    is_relevant_project: bool = False
    name: Optional[str] = None
    description: Optional[str] = None
    problem_solved: Optional[str] = None
    target_users: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    technology: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    supporting_excerpt: Optional[str] = None   # verbatim text from the page


class ProjectComparisonOut(BaseModel):
    shared_features: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    possible_gaps: list[str] = Field(default_factory=list)  # hypotheses
    explanation: str = ""


class StakeholderItem(BaseModel):
    name: str
    description: str = ""


class StakeholderList(BaseModel):
    groups: list[StakeholderItem] = Field(default_factory=list)


class ExtractedNeed(BaseModel):
    stakeholder_group: str
    need_text: str
    excerpt: str                      # exact quote, validated against the page
    evidence_type: Literal["review", "forum", "survey", "paper", "report", "interview"] = "forum"
    stance: Literal["reports_problem", "disputes_problem"] = "reports_problem"


class ExtractedNeedList(BaseModel):
    needs: list[ExtractedNeed] = Field(default_factory=list)


class NeedAnalysis(BaseModel):
    ai_interpretation: str = ""
    missing_information: list[str] = Field(default_factory=list)
    validation_question: str = ""
