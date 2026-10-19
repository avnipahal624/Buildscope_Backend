from app.llm.prompts import ANALYSIS_SYSTEM
from app.llm.schemas import NeedAnalysis


def analyse_need(llm, need_text: str, group: str, evidence: list[tuple[str, str, str]]) -> NeedAnalysis:
    """evidence = [(relation, excerpt, url)]. The output is stored in separate AI fields."""
    lines = "\n".join(f"- [{rel}] ({url}) \"{ex}\"" for rel, ex, url in evidence)
    user = (f"Stakeholder group: {group}\nCandidate need: {need_text}\n\n"
            f"Verbatim evidence collected:\n<document>\n{lines}\n</document>")
    return llm.complete_json(ANALYSIS_SYSTEM, user, NeedAnalysis)
