"""LLM-generated comparison of the user's project with one discovered project."""
import json

from app.llm.prompts import COMPARE_SYSTEM
from app.llm.schemas import ProjectComparisonOut
from app.models import Project, SimilarProject
from app.research.extraction import project_profile


def compare(llm, project: Project, sp: SimilarProject) -> ProjectComparisonOut:
    record = {
        "name": sp.name, "description": sp.description, "problem_solved": sp.problem_solved,
        "target_users": sp.target_users, "features": sp.features,
        "technology": sp.technology, "limitations": sp.limitations,
    }
    user = (f"User's project:\n{project_profile(project)}\n\n"
            f"Existing project (data extracted from {sp.source_url}):\n{json.dumps(record, indent=2)}")
    return llm.complete_json(COMPARE_SYSTEM, user, ProjectComparisonOut)
