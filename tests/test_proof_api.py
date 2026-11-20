"""Persisted proof chain contract used by the Passport after navigation and refresh."""
from app import deps, db as database
from app.models import Opportunity, ResearchRun
from app.chain import RequirementDraft
from tests.conftest import FakeLLM, FakeAdapter


def test_requirement_verification_round_trip(client):
    llm = FakeLLM()
    llm.handlers['RequirementDraft'] = lambda _: RequirementDraft(
        text='The system shall show a project summary.',
        acceptance_test='Open the project and check the summary is visible.',
    )
    deps.override(adapter_factory=lambda: FakeAdapter({}, lambda _: []), llm_factory=lambda: llm)
    project_id = client.post('/api/projects', json={
        'name': 'Proof demo', 'description': 'A project with a testable requirement.',
        'target_users': ['students'],
    }).json()['id']
    with database.get_session_factory()() as session:
        run = ResearchRun(project_id=project_id, kind="research", status="completed")
        session.add(run)
        session.flush()
        opportunity = Opportunity(project_id=project_id, run_id=run.id, description='Show the project summary',
                                  rationale='Users need context', origin='research_gap', status='hypothesis')
        session.add(opportunity)
        session.commit()
        opportunity_id = opportunity.id
    first = client.get(f'/opportunities/{opportunity_id}/chain').json()
    assert first['requirements'] == []
    created = client.post(f'/opportunities/{opportunity_id}/requirement')
    assert created.status_code == 200, created.text
    requirement_id = created.json()['id']
    restored = client.get(f'/opportunities/{opportunity_id}/chain').json()
    assert restored['requirements'][0]['id'] == requirement_id
    assert restored['requirements'][0]['acceptance_test'] == created.json()['acceptance_test']
    verified = client.post(f'/requirements/{requirement_id}/verify')
    assert verified.status_code == 200
    assert verified.json()[0]['result'] == 'fail'  # no linked evidence
    again = client.get(f'/opportunities/{opportunity_id}/chain').json()
    assert again['requirements'][0]['verification'][0]['result'] == 'fail'


def test_local_frontend_cors(client):
    response = client.options('/api/projects', headers={
        'Origin': 'http://localhost:5173',
        'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
