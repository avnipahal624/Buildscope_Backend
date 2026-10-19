"""Module 2 - Research Analysis pipeline (runs inside a background job)."""
from sqlalchemy.orm import Session

from app.config import Settings
from app.llm.prompts import QUERY_SYSTEM
from app.llm.schemas import QueryList
from app.models import (Claim, Evidence, Opportunity, Project, ProjectComparison, ResearchRun,
                        SimilarProject)
from app.research import comparison, extraction, similarity, sourcing
from app.runlog import COVERAGE_NOTE, RunLog, checkpoint


def _fallback_queries(p: Project) -> list[str]:
    base = " ".join((p.keywords or [])[:3]) or p.name
    return [f"{base} app", f"{base} alternatives", f"{base} open source github",
            f"{base} for {(p.target_users or ['users'])[0]}"]


def generate_queries(llm, p: Project, settings: Settings, log: RunLog) -> list[str]:
    from app.research.extraction import project_profile
    try:
        out = llm.complete_json(
            QUERY_SYSTEM,
            f"Project:\n{project_profile(p)}\n\nWrite up to {settings.max_queries_per_run} queries.",
            QueryList)
        queries = [q.strip() for q in out.queries if q.strip()]
    except Exception as e:
        log.warn(f"query generation failed, using fallback templates: {e}")
        queries = []
    seen, uniq = set(), []
    for q in queries or _fallback_queries(p):
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq[:settings.max_queries_per_run]


def run_research(db: Session, run: ResearchRun, adapter, llm, settings: Settings) -> str:
    """Returns the final status string."""
    log = RunLog()
    project = db.get(Project, run.project_id)
    run.model_version, run.prompt_version = llm.model, settings.prompt_version

    # 1-2. queries (stored so the run is reproducible)
    run.queries = generate_queries(llm, project, settings, log)
    checkpoint(db, run, log, "searching")

    # 3. discover
    hits, failed_searches = sourcing.discover(adapter, run.queries, log)
    if failed_searches == len(run.queries):
        run.error = "every search query failed"
        checkpoint(db, run, log, "failed")
        return "failed"
    candidates = sourcing.select(hits, settings, log)
    checkpoint(db, run, log, "fetching", search_hits=len(hits), selected=len(candidates))

    # 4-5. fetch + clean + dedupe
    sources, stats = sourcing.fetch_and_store(db, adapter, candidates, settings, log)
    if candidates and stats["failed"] == len(candidates) - stats["cached"] and not sources:
        run.error = "every page fetch failed"
        checkpoint(db, run, log, "failed", **stats)
        return "failed"
    checkpoint(db, run, log, "extracting", **stats)

    # 6. structured extraction + verification
    extracted: list[tuple] = []
    for src in sources:
        try:
            res = extraction.extract_project(llm, src, project, settings)
        except Exception as e:
            log.error(f"extraction failed for {src.url}: {e}")
            continue
        if res is None:
            continue
        if not res.excerpt_verified:
            log.warn(f"excerpt for {src.url} not found in page text; confidence set to low")
        if res.dropped_ungrounded:
            log.warn(f"{src.url}: dropped {res.dropped_ungrounded} ungrounded feature(s)/limitation(s)")
        extracted.append((src, res))
    checkpoint(db, run, log, "ranking", extracted=len(extracted))

    # 7. similarity ranking
    cand_dicts = [r.data.model_dump() for _, r in extracted]
    try:
        scores = similarity.score_projects(llm, project, cand_dicts) if extracted else []
    except Exception as e:
        log.error(f"similarity scoring failed: {e}")
        scores = [(0.0, {})] * len(extracted)

    rows: list[SimilarProject] = []
    for (src, res), (score, comps) in zip(extracted, scores):
        d = res.data
        sp = SimilarProject(
            project_id=project.id, run_id=run.id, source_id=src.id, name=d.name.strip(),
            source_url=src.url, description=d.description, problem_solved=d.problem_solved,
            target_users=d.target_users, features=d.features, technology=d.technology,
            limitations=d.limitations, supporting_excerpt=d.supporting_excerpt,
            excerpt_verified=res.excerpt_verified, similarity_score=score, score_components=comps,
            extraction_confidence=res.confidence, model_version=llm.model,
            prompt_version=settings.prompt_version, collected_at=src.retrieved_at,
        )
        db.add(sp)
        rows.append(sp)
        # Module 7 hook: record a claim + verbatim evidence for each discovered project
        if d.supporting_excerpt and res.excerpt_verified:
            claim = Claim(project_id=project.id, claim_type="project_description",
                          text=f"{d.name}: {d.description or 'existing project'}", created_by="ai")
            db.add(claim)
            db.flush()
            db.add(Evidence(project_id=project.id, run_id=run.id, source_id=src.id,
                            claim_id=claim.id, excerpt=d.supporting_excerpt, relation="supports",
                            evidence_type="website", excerpt_verified=True,
                            retrieved_at=src.retrieved_at))
    db.commit()
    rows.sort(key=lambda r: r.similarity_score, reverse=True)

    # 8-9. comparisons for the top-K, gaps recorded as hypotheses
    checkpoint(db, run, log, "comparing")
    seen_gaps: set[str] = set()
    for sp in rows[:settings.comparison_top_k]:
        try:
            out = comparison.compare(llm, project, sp)
        except Exception as e:
            log.error(f"comparison failed for {sp.name}: {e}")
            continue
        db.add(ProjectComparison(
            project_id=project.id, run_id=run.id, similar_project_id=sp.id,
            shared_features=out.shared_features, differences=out.differences,
            possible_gaps=out.possible_gaps, explanation=out.explanation,
            supporting_source_ids=[sp.source_id], model_version=llm.model))
        for gap in out.possible_gaps[:3]:
            if gap.strip().lower() in seen_gaps:
                continue
            seen_gaps.add(gap.strip().lower())
            db.add(Opportunity(
                project_id=project.id, run_id=run.id, origin="research_gap", description=gap,
                rationale=f"Suggested while comparing with {sp.name}. Hypothesis only: a feature "
                          "not being documented does not prove an unmet need.",
                linked_project_ids=[sp.id], status="hypothesis"))
    db.commit()

    # 10. finish: never report partial failure as full success
    scope_info = {
        "queries_run": len(run.queries), "failed_searches": failed_searches,
        "pages_fetched_or_cached": len(sources), "projects_extracted": len(rows),
        "coverage_note": COVERAGE_NOTE, **stats,
    }
    final = "completed_with_errors" if log.errors else "completed"
    checkpoint(db, run, log, "done", **scope_info)
    return final
