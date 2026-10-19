"""LLM structured extraction of one project from one page, followed by verification."""
from dataclasses import dataclass

from app.config import Settings
from app.llm.prompts import PROJECT_EXTRACT_SYSTEM
from app.llm.schemas import ExtractedProject
from app.models import Project, Source
from app.research.cleaning import excerpt_in_text, is_grounded


def project_profile(p: Project) -> str:
    return (
        f"Name: {p.name}\nDescription: {p.description}\nProblem: {p.problem_statement}\n"
        f"Target users: {', '.join(p.target_users or [])}\n"
        f"Planned features: {', '.join(p.planned_features or [])}\n"
        f"Keywords: {', '.join(p.keywords or [])}"
    )


@dataclass
class ExtractionResult:
    data: ExtractedProject
    excerpt_verified: bool
    confidence: str          # high | medium | low
    dropped_ungrounded: int


def extract_project(llm, source: Source, project: Project, settings: Settings) -> ExtractionResult | None:
    text = source.content or ""
    user = (
        f"User's project (used only to judge relevance):\n{project_profile(project)}\n\n"
        f"Source URL: {source.url}\n\n<document>\n{text[:settings.max_page_chars_for_llm]}\n</document>"
    )
    data = llm.complete_json(PROJECT_EXTRACT_SYSTEM, user, ExtractedProject)
    if not data.is_relevant_project or not (data.name or "").strip():
        return None

    verified = excerpt_in_text(data.supporting_excerpt, text)
    # Drop features/limitations whose words do not appear on the page (likely invented).
    kept_features = [f for f in data.features if is_grounded(f, text)]
    kept_limits = [x for x in data.limitations if is_grounded(x, text)]
    dropped = (len(data.features) - len(kept_features)) + (len(data.limitations) - len(kept_limits))
    data.features, data.limitations = kept_features, kept_limits
    if not verified:
        data.supporting_excerpt = data.supporting_excerpt  # kept for audit, flagged unverified

    if verified and data.description and data.features and dropped == 0:
        confidence = "high"
    elif verified:
        confidence = "medium"
    else:
        confidence = "low"
    return ExtractionResult(data, verified, confidence, dropped)
