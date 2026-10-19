"""Module 3 - Stakeholder Intelligence pipeline (runs inside a background job)."""
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Claim, Evidence, ResearchRun, Project, Stakeholder, StakeholderNeed
from app.research import sourcing
from app.runlog import RunLog, checkpoint
from app.stakeholders import analysis, evidence as ev, identify, linking
from app.stakeholders.strength import assess_strength
from app.research.cleaning import registered_domain  # noqa: F401


def latest_run_id(db: Session, project_id: str, kind: str) -> str | None:
    run = (db.query(ResearchRun)
           .filter(ResearchRun.project_id == project_id, ResearchRun.kind == kind,
                   ResearchRun.status.in_(["completed", "completed_with_errors"]))
           .order_by(ResearchRun.created_at.desc()).first())
    return run.id if run else None


def run_stakeholder_analysis(db: Session, run: ResearchRun, adapter, llm, settings: Settings) -> str:
    log = RunLog()
    project = db.get(Project, run.project_id)
    run.model_version, run.prompt_version = llm.model, settings.prompt_version

    # 1. stakeholder groups (AI-suggested until a user confirms them)
    groups = db.query(Stakeholder).filter(Stakeholder.project_id == project.id,
                                          Stakeholder.status != "rejected").all()
    if not groups:
        identify.identify_stakeholders(db, llm, project, settings)
        groups = db.query(Stakeholder).filter(Stakeholder.project_id == project.id,
                                              Stakeholder.status != "rejected").all()
    # confirmed groups first
    groups = sorted(groups, key=lambda g: g.status != "confirmed")[:settings.max_stakeholder_groups]
    if not groups:
        run.error = "no stakeholder groups could be identified"
        checkpoint(db, run, log, "failed")
        return "failed"

    # 2. collect evidence
    run.queries = ev.build_queries(project, groups, settings)
    checkpoint(db, run, log, "searching", groups=[g.name for g in groups])
    hits, failed = sourcing.discover(adapter, run.queries, log)
    if failed == len(run.queries):
        run.error = "every search query failed"
        checkpoint(db, run, log, "failed")
        return "failed"
    candidates = sourcing.select(hits, settings, log)
    checkpoint(db, run, log, "fetching", search_hits=len(hits), selected=len(candidates))
    sources, stats = sourcing.fetch_and_store(db, adapter, candidates, settings, log)
    if candidates and not sources and stats["failed"]:
        run.error = "every page fetch failed"
        checkpoint(db, run, log, "failed", **stats)
        return "failed"

    # 3-4. extract candidate needs; discard any whose excerpt is not on the page
    checkpoint(db, run, log, "extracting", **stats)
    raw = []
    for src in sources:
        try:
            for n in ev.extract_needs(llm, src, project, groups, settings, log):
                raw.append((src, n))
        except Exception as e:
            log.error(f"need extraction failed for {src.url}: {e}")

    # cluster + persist (claims, needs, verbatim evidence)
    checkpoint(db, run, log, "clustering", verified_statements=len(raw))
    try:
        clusters = ev.cluster_needs(llm, raw, settings)
    except Exception as e:
        log.error(f"clustering failed: {e}")
        clusters = []
    group_by_name = {g.name: g for g in groups}
    needs: list[StakeholderNeed] = []
    evidence_rows: dict[str, list[tuple[str, str, str]]] = {}
    for c in clusters:
        group = group_by_name[c.group]
        claim = Claim(project_id=project.id, claim_type="stakeholder_need",
                      text=f"{group.name}: {c.need_text}", created_by="ai")
        db.add(claim)
        db.flush()
        need = StakeholderNeed(project_id=project.id, run_id=run.id, stakeholder_id=group.id,
                               claim_id=claim.id, need_text=c.need_text,
                               model_version=llm.model, prompt_version=settings.prompt_version)
        db.add(need)
        db.flush()
        tuples = []
        for src, item, relation in c.items:
            db.add(Evidence(project_id=project.id, run_id=run.id, source_id=src.id, claim_id=claim.id,
                            need_id=need.id, excerpt=item.excerpt, relation=relation,
                            evidence_type=item.evidence_type, excerpt_verified=True,
                            retrieved_at=src.retrieved_at))
            tuples.append((relation, item.excerpt, src.url))
        evidence_rows[need.id] = tuples
        needs.append(need)
    db.commit()

    # 5-6. AI analysis (separate fields) and rule-based evidence strength
    checkpoint(db, run, log, "analysing", needs=len(needs))
    for need in needs:
        tuples = evidence_rows[need.id]
        s = assess_strength(tuples, settings.strong_support_min_domains)
        need.evidence_status, need.need_type = s.status, s.need_type
        need.supporting_count, need.contradicting_count = s.supporting, s.contradicting
        need.independent_source_count = s.independent_sources
        try:
            a = analysis.analyse_need(llm, need.need_text, db.get(Stakeholder, need.stakeholder_id).name, tuples)
            need.ai_interpretation = a.ai_interpretation
            need.missing_information = a.missing_information
            need.validation_question = a.validation_question
        except Exception as e:
            log.error(f"AI analysis failed for need '{need.need_text[:50]}': {e}")
    db.commit()

    # 7. bridge to Module 2 results, then opportunity hypotheses
    checkpoint(db, run, log, "linking")
    research_run = latest_run_id(db, project.id, "research")
    if research_run is None:
        log.warn("no completed research run found: needs were not linked to existing solutions")
    try:
        links = linking.link_needs(db, llm, run.id, project.id, needs, research_run, settings)
        opps = linking.derive_opportunities(db, run.id, project.id, needs)
    except Exception as e:
        log.error(f"linking failed: {e}")
        links = opps = 0

    final = "completed_with_errors" if log.errors else "completed"
    checkpoint(db, run, log, "done", needs_found=len(needs), links_created=links,
               opportunities_created=opps, linked_research_run=research_run,
               coverage_note="A handful of online statements cannot show how common a need is. "
                             "Statuses describe evidence strength, not market proof.", **stats)
    return final
