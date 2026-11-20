# BuildScope security audit

## Scope

The audit covers the FastAPI routers, authentication dependency, project and nested investigation resources, background-job lookup, requirements, verification and proof-chain endpoints.

## Corrections applied

- Project reads and research runs are filtered by the authenticated owner.
- Job status lookup now checks the job's project owner.
- Stakeholder updates now resolve the stakeholder's project and enforce ownership.
- Project requirements now reject projects owned by another account on both create and list.
- Opportunity listing in the proof-chain router is owner-filtered.
- Requirement generation, verification and proof-chain retrieval resolve the opportunity's project before performing work.
- Authentication fails closed when `BUILDSCOPE_AUTH_SECRET` is absent in a deployed server.

## Evidence integrity

Evidence excerpts remain separate from AI interpretations. Verification only reports an excerpt match when the stored excerpt is present in the retrieved source content; URL reachability is reported as a separate check and is not treated as proof of the claim.

## Remaining risks

- The current schema still uses `create_all` plus a compatibility `owner_id` migration; production should move to versioned Alembic migrations before schema evolution.
- Rate limiting is not yet enforced at the application edge. Put an authenticated rate limiter/API gateway in front of expensive research and GitHub search routes.
- Background jobs currently use FastAPI `BackgroundTasks`; a durable queue is recommended for multi-instance deployments.
- Cross-user tests should be expanded as new resource tables are introduced.

## Verification

`pytest -q` passes with 23 tests. The suite covers source safety, evidence provenance, pipeline failure handling and API workflow behavior. Production authentication was separately checked against the deployed Render service.
