# BuildScope AI backend: Research Analysis + Stakeholder Intelligence

Step-by-step guide for running, understanding and extending your two modules.

**What is verified and what is not.** The 23 automated tests pass using fake TinyFish and fake LLM
services on SQLite. That proves the pipeline logic, the data rules and the API. It does **not**
prove the code works against the real TinyFish, your real LLM, or PostgreSQL. Part 3 gives you
scripts to check each of those in minutes. Expect to fix small things (for example a field name
in a TinyFish response) when you first run live.

---

## Part 1: Prerequisites

| Need | Why | Where |
|---|---|---|
| Python 3.11+ | runs the backend | python.org |
| Docker Desktop | runs PostgreSQL | docker.com |
| TinyFish API key | web search and page fetch | https://agent.tinyfish.ai/api-keys |
| LLM API key | extraction, comparison, analysis | OpenAI, or any OpenAI-compatible provider |
| Embeddings access | similarity ranking | usually the same provider as the LLM |
| Git + VS Code | normal development | |

Per the TinyFish docs, Search and Fetch are free at the time of writing. Confirm quotas and terms
on their site before a real run.

---

## Part 2: Setup (about 15 minutes)

```bash
# 1. unzip and enter the project
unzip buildscope-backend.zip && cd buildscope-backend

# 2. virtual environment
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

# 3. dependencies
pip install -r requirements.txt

# 4. configuration
cp .env.example .env                # Windows: copy .env.example .env
#    open .env and fill in TINYFISH_API_KEY, LLM_API_KEY (and LLM_MODEL if you want another model)

# 5. database
docker compose up -d

# 6. run the tests (no keys, no database needed)
python -m pytest -q                 # expect: 23 passed

# 7. start the server
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs. You get an interactive page where every endpoint can be tried.
Tables are created automatically on first start.

---

## Part 3: Verify each external service separately

Do these before running the full pipeline, so you know which piece is at fault if something breaks.

```bash
python -m scripts.check_tinyfish "student assignment manager app"
python -m scripts.check_llm
```

* `check_tinyfish` prints search results and the start of two fetched pages. If titles or
  snippets are blank, open `app/research/adapter.py` and adjust the field names in `search()`
  and `fetch()` to match what TinyFish actually returns. That is the only file that knows
  about TinyFish.
* `check_llm` calls the chat API and the embeddings API.
  * **Different embedding provider?** Set `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`,
    `EMBEDDING_MODEL` in `.env`.
  * **Different chat provider?** Any API that accepts the OpenAI `/chat/completions` format with
    `response_format: {"type": "json_object"}` works by changing `LLM_BASE_URL` and `LLM_MODEL`.
    If your provider does not support that format, edit only `complete_json()` in
    `app/llm/client.py`.

---

## Part 4: Run the whole flow

With the server running:

```bash
python -m scripts.demo_flow
```

It creates a sample project, starts research, then stakeholder analysis, polls the job status,
prints a summary and writes `report.json`. Or do it by hand in `/docs`:

1. `POST /api/projects` with your idea. Copy the `id`.
2. `POST /api/projects/{id}/research` returns `{"job_id": ...}`.
3. `GET /api/jobs/{job_id}` until status is `completed` or `completed_with_errors`.
   The `scope.stage` field shows progress. `log` lists every warning and error.
4. (Optional) `POST /api/projects/{id}/stakeholders/identify`, then `PATCH /api/stakeholders/{sid}`
   with `{"status": "confirmed"}` or `"rejected"` to curate groups before evidence collection.
5. `POST /api/projects/{id}/stakeholders/analyze`, then poll the job again.
6. Read results: `/similar-projects`, `/comparisons`, `/stakeholders`, `/needs`, `/evidence`,
   `/opportunities`, `/report`.

**Job statuses:** `pending`, `running`, `completed`, `completed_with_errors` (some pages or calls
failed, see `log`), `failed` (nothing usable, see `error`). A partial failure is never reported as
plain `completed`.

---

## Part 5: How it works

### 5.1 File map

```
app/
  main.py            FastAPI app, creates tables, fails orphaned jobs on restart
  config.py          settings from .env (limits, thresholds, URLs)
  db.py              engine + sessions
  models.py          ALL tables (read this first)
  schemas.py         API response models
  deps.py            factories for TinyFish + LLM (tests swap in fakes)
  jobs.py            runs a job in the background, records status/usage
  runlog.py          warnings/errors + progress checkpoints
  api/routes.py      every endpoint
  llm/
    client.py        ONE wrapper: complete_json() and embed()
    schemas.py       Pydantic schemas the LLM must fill
    prompts.py       every prompt (bump prompt_version when you edit)
  research/
    adapter.py       TinyFish search() + fetch()  <- only provider-specific file
    safety.py        URL checks (SSRF protection)
    cleaning.py      URL normalising, dedupe, excerpt matching, grounding check
    sourcing.py      search -> filter -> fetch -> cache -> dedupe (used by both modules)
    extraction.py    page text -> structured project, then verification
    similarity.py    hybrid scoring
    comparison.py    LLM comparison of one project vs yours
    pipeline.py      Module 2 orchestration
  stakeholders/
    identify.py      suggest stakeholder groups
    evidence.py      queries, need extraction, excerpt check, clustering
    strength.py      evidence-strength rules (plain code, no LLM)
    analysis.py      AI interpretation, kept in separate fields
    linking.py       need -> existing features/limitations, opportunity hypotheses
    pipeline.py      Module 3 orchestration
tests/               23 tests, fully offline
scripts/             live checks + demo
```

### 5.2 Module 2 pipeline (`research/pipeline.py`)

1. **Queries.** The LLM writes up to `MAX_QUERIES_PER_RUN` varied queries. If that fails, template
   queries are used. They are saved on the run so it is reproducible.
2. **Search.** Each query goes through `adapter.search()`. A failed query is logged and skipped.
   If every query fails, the run is `failed`.
3. **Select.** Skips video/social domains, rejects unsafe URLs (private IPs, non-http, credentials),
   and caps at `MAX_SOURCES_PER_RUN`.
4. **Fetch and store.** Pages fetched within `FETCH_CACHE_DAYS` come from the database instead of
   TinyFish. New pages go to `adapter.fetch()` in batches of 10. Failures are stored with the error.
5. **Deduplicate.** Same URL after normalisation (tracking parameters and fragments removed),
   identical content hash, or near-identical text (shingle similarity of 0.9 or more).
6. **Extract.** One LLM call per page fills `ExtractedProject`. Then code verifies:
   * `supporting_excerpt` must literally appear in the page, otherwise `excerpt_verified=false`
     and confidence is `low`.
   * Each feature/limitation must share most of its words with the page, otherwise it is dropped.
   * Unknown fields stay `null`.
7. **Rank.** Score = weighted mix of description similarity (0.40, embeddings), problem similarity
   (0.25), target-user overlap (0.15) and feature overlap (0.20). A missing signal is excluded and
   the weights are renormalised rather than counted as zero. Components are stored per project in
   `score_components`.
8. **Compare.** The top `COMPARISON_TOP_K` get an LLM comparison from the extracted record only
   (not raw page text). "Possible gaps" are saved as `Opportunity` rows with `status=hypothesis`.
9. **Finish.** `scope` stores queries run, pages fetched, projects found and a coverage note:
   *absence of a match is not evidence the idea is original.*

### 5.3 Module 3 pipeline (`stakeholders/pipeline.py`)

1. **Groups.** Existing non-rejected groups are used (confirmed first). If none exist, the LLM
   suggests some, stored as `suggested`.
2. **Evidence search.** Templated queries per group (problems, frustrations, surveys).
3. **Extract needs.** One LLM call per page, with the group names supplied. Any item whose
   `excerpt` is not found in the page text is **discarded**. This is the main defence against
   invented quotes.
4. **Cluster.** Similar need statements (embedding cosine of `NEED_CLUSTER_THRESHOLD` or more) merge
   into one need with several evidence rows. Statements that dispute a need attach to the closest
   need at a lower threshold (`DISPUTE_ATTACH_THRESHOLD`) and are stored with
   `relation=contradicts`.
5. **Strength.** `stakeholders/strength.py`, plain code:

   | Status | Rule |
   |---|---|
   | `unverified` | no evidence |
   | `supported` | supporting evidence from fewer than 3 independent domains |
   | `strongly_supported` | supporting evidence from `STRONG_SUPPORT_MIN_DOMAINS` (default 3) or more independent domains |
   | `conflicting` | both supporting and contradicting evidence |
   | `needs_further_research` | only contradicting evidence |

   Copied excerpts count once. Many pages on one domain count as one source (this is
   conservative: five Reddit threads are still "one source").
   `need_type`: `hypothesis` (no support), `explicit` (one independent source), `pattern` (two or more).
6. **AI analysis.** Interpretation, missing information and a validation question are stored in
   their own columns (`ai_interpretation`, `missing_information`, `validation_question`), never mixed
   with quotes in `evidence`.
7. **Link and derive.** Each need is matched, by embedding, to features and limitations from the
   latest research run (`need_solution_links`). For needs that are `supported` or
   `strongly_supported`: a related *limitation* produces an opportunity hypothesis, and *no related
   feature at all* produces an "investigate" hypothesis. Wording is written by code, so nothing is
   invented. Needs already covered by documented features produce no opportunity.

### 5.4 Safety rules and where they are enforced

| Rule | Enforced in | Test |
|---|---|---|
| Never invent quotes | `cleaning.excerpt_in_text` used by both pipelines | `test_excerpt_matching...`, e2e hallucinated quote |
| Unknown stays unknown | `llm/prompts.py` + nullable columns | e2e `problem_solved is None` |
| Ungrounded features dropped | `cleaning.is_grounded` | e2e "blockchain" feature |
| Copies are not independent evidence | `strength.assess_strength` | `test_copies_and_same_domain...` |
| Contradictions recorded | `evidence.cluster_needs` | e2e `conflicting` |
| AI separate from quotes | `models.StakeholderNeed` columns | e2e |
| SSRF protection | `research/safety.py` | `test_unsafe_urls_rejected` |
| Prompt injection | `<document>` delimiters + `SAFETY` prompt, LLM has no tools | e2e injection page |
| No false success | `pipeline` status logic | e2e `completed_with_errors`, `failed` |
| Reproducibility | stored queries, `model_version`, `prompt_version`, token usage | e2e |
| Never claim originality | `runlog.COVERAGE_NOTE` in run scope | e2e |

Prompt injection is reduced, not eliminated. The strongest protections are structural: the model's
output is validated against a schema, excerpts are verified against the page, and the model cannot
take actions.

---

## Part 6: Database

Tables (see `app/models.py`): `projects`, `research_runs`, `sources`, `claims`, `evidence`,
`similar_projects`, `project_comparisons`, `stakeholders`, `stakeholder_needs`,
`need_solution_links`, `opportunities`.

Inspect with:

```bash
docker compose exec db psql -U buildscope -c "select name, similarity_score, extraction_confidence from similar_projects order by similarity_score desc;"
docker compose exec db psql -U buildscope -c "select evidence_status, need_text from stakeholder_needs;"
```

Notes:
* `research_runs` doubles as the job table. Its `id` is the job id.
* `projects`, `sources`, `claims`, `evidence` are **stubs** for Module 1 and Module 7. Agree the
  real schema with those owners (Part 8).
* Tables are created with `create_all`. When the schema settles, add Alembic migrations.
* To reset everything in development: `docker compose down -v && docker compose up -d`.

---

## Part 7: Configuration

All in `.env` (defaults in `app/config.py`):

| Setting | Default | Effect |
|---|---|---|
| `MAX_SOURCES_PER_RUN` | 12 | pages fetched per run (main cost control) |
| `MAX_QUERIES_PER_RUN` | 5 | searches per run |
| `COMPARISON_TOP_K` | 5 | how many projects get an LLM comparison |
| `FETCH_CACHE_DAYS` | 7 | reuse stored pages instead of refetching |
| `STRONG_SUPPORT_MIN_DOMAINS` | 3 | independent domains needed for `strongly_supported` |
| `NEED_CLUSTER_THRESHOLD` | 0.80 | how alike two need statements must be to merge |
| `LINK_THRESHOLD` | 0.55 | how alike a need and a feature must be to link |
| `MAX_STAKEHOLDER_GROUPS` | 4 | groups analysed per run |

The thresholds depend on your embedding model. Tune them by looking at real output: if unrelated
needs are merged, raise `NEED_CLUSTER_THRESHOLD`; if obvious links are missed, lower
`LINK_THRESHOLD`.

Cost per run is roughly: `MAX_QUERIES` searches + `MAX_SOURCES` fetches + about `MAX_SOURCES`
extraction calls per module + `COMPARISON_TOP_K` comparisons + one analysis call per need + a few
embedding calls. Each job stores its token counters in `usage`, so measure real cost before setting
any limits for users.

---

## Part 8: What to agree with teammates

1. **Module 1 (intake).** You use `projects(id, name, description, problem_statement, target_users,
   keywords, planned_features)`. When Module 1 exists, replace the stub project endpoints and keep
   those column meanings. Only approved requirements should feed research.
2. **Module 7 (evidence).** You write `sources`, `claims`, `evidence`. Agree columns, relation values
   (`supports`/`contradicts`) and status names. Your `evidence.excerpt_verified` means
   "found verbatim in the fetched page". Whether it truly supports the claim is a separate check.
3. **Module 4 (opportunity).** They read `project_comparisons`, `stakeholder_needs` (with
   `evidence_status`), `need_solution_links` and `opportunities` (all hypotheses).
4. **Module 5 (planning).** They can read `similar_projects.technology`.
5. **Graph.** Stable IDs are string UUIDs: `stakeholder_needs.id`, `evidence.id`,
   `similar_projects.id`, `opportunities.id`, `claims.id`.
6. **Vocabularies.** Agree one list for evidence statuses and `source_type` values.

---

## Part 9: Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Job `failed`: "TINYFISH_API_KEY is not configured" | `.env` missing or key blank. Restart uvicorn after editing `.env`. |
| Job `failed`: "every search query failed" | key wrong, quota hit, or response shape changed. Run `scripts.check_tinyfish`. |
| Job `failed`: "LLM API key is not configured" | set `LLM_API_KEY`. |
| `HTTP 400` from LLM in the job log | provider rejects `response_format`. Edit `complete_json()`. |
| Many "excerpt not found in page text" warnings | the LLM paraphrases. Lower the temperature, use a stronger model, or check the page text really contains the quote (JS-heavy pages). |
| Zero similar projects | queries too narrow, or pages judged irrelevant. Read `queries` and `log` in the job. |
| Every need is `supported`, never `strongly_supported` | too few independent domains in results; raise `MAX_SOURCES_PER_RUN` or search more varied sources. |
| Job stuck on `pending` | the server restarted. Orphaned jobs are marked `failed` on the next start; just run again. |
| `connection refused` on 5432 | `docker compose up -d`, wait a few seconds. |

---

## Part 10: Known limitations (be honest about these in your report)

* **Not yet run against live services.** Verified offline only (Part 3 closes the gap).
* **Background jobs are not resumable.** FastAPI background tasks die with the server. A job that
  is interrupted must be restarted. For real resumability, move `execute_run` to Celery or RQ with
  Redis. The pipelines are plain functions, so only `jobs.py` and the two start endpoints change.
* **No authentication or per-user access control.**
* **Independence is approximated by domain.** Two sites republishing the same text with different
  wording look independent. Real independence needs human review.
* **Excerpt verification checks existence, not meaning.** A real sentence can still be attached to
  the wrong need. Sample and review these by hand.
* **Similarity weights and thresholds are untuned starting points.** Measure before trusting them.
* **Pages are truncated to `MAX_PAGE_CHARS_FOR_LLM` (12,000 characters)** for extraction; long pages
  may lose content.
* **Stakeholder evidence from the public web is thin.** A few comments cannot show prevalence;
  statuses describe evidence strength only. Interviews and surveys should be added as an evidence type.

---

## Part 11: Suggested next steps

1. Run the live checks, then `demo_flow`, and read `report.json` critically.
2. Hand-label about 30 discovered projects as relevant or not, then compute Precision@K of the
   ranking and tune weights. Do the same for need extraction (does each excerpt really support its
   need?). Do not quote an accuracy figure until you have done this.
3. Agree the shared schema with Module 7 and Module 1 owners.
4. Add Alembic migrations.
5. Move jobs to Celery/RQ if you need resumability.
6. Add a user interface for confirming stakeholder groups and reviewing evidence.
7. Add direct stakeholder interviews or surveys as a new `evidence_type`.

---

## Part 12: Where to change things

| I want to... | Edit |
|---|---|
| use another search provider | implement `search`/`fetch` in a new class like `TinyFishAdapter`, change `deps.py` |
| change what is extracted | `llm/schemas.py` (fields) and `llm/prompts.py` (instructions), then the model in `models.py` |
| change evidence-strength rules | `stakeholders/strength.py` and its tests |
| change similarity weights | `WEIGHTS` in `research/similarity.py` |
| add a stakeholder search template | `build_queries` in `stakeholders/evidence.py` |
| change opportunity wording | `derive_opportunities` in `stakeholders/linking.py` |
