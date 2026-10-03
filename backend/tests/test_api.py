from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app


def test_health_and_query_end_to_end():
    # The test suite uses its isolated test database configuration; production defaults to PostgreSQL.
    with TestClient(app) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json()['products'] > 0

        response = client.post('/api/query', json={'query': 'I need a CRM for a 20-person sales team that integrates with Slack.'})
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'complete'
        assert len(data['recommendations']) == 3
        assert data['recommendations'][0]['product']['category'] == 'CRM'
        assert data['recommendations'][0]['hard_constraints_satisfied'] is True


def test_frontend_does_not_reset_catalog_on_page_load():
    from pathlib import Path
    react_app = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'App.jsx'
    text = react_app.read_text(encoding='utf-8')
    assert "/api/catalog/reset-demo" in text
    assert 'const [stats, setStats]' in text
    assert 'useEffect(() => { refresh() }, [refresh])' in text



def test_api_is_attempted_before_fallback_for_full_query(monkeypatch):
    from app.main import llm
    from app.core.llm import LLMResult

    calls = []

    async def understand(*args, **kwargs):
        calls.append('understand')
        return LLMResult({'category': 'CRM', 'team_size': 20, 'integrations': ['Slack'], 'features': [], 'deployment': [], 'pricing_tier': '$$', 'confidence': 0.95}, True, False)

    async def rerank(*args, **kwargs):
        calls.append('rerank')
        return LLMResult({'ordered_product_ids': [c['id'] for c in args[2]][::-1]}, True, False)

    async def explain(*args, **kwargs):
        calls.append('explain')
        recs = args[2]
        return LLMResult({'recommendations': [
            {'product_id': r['product_id'], 'why_recommended': [f"{r['product_name']} matches {r['matched_requirements'][0] if r['matched_requirements'] else 'the request'}"], 'improve_fit': ['Verify plan limits before purchase']}
            for r in recs
        ]}, True, False)

    monkeypatch.setattr(llm, 'understand', understand)
    monkeypatch.setattr(llm, 'rerank', rerank)
    monkeypatch.setattr(llm, 'explain', explain)
    with TestClient(app) as client:
        response = client.post('/api/query', json={'query': 'CRM for 20 users with Slack', 'top_k': 3})
    assert response.status_code == 200
    trace = response.json()['trace']['api_trace']
    assert trace['requirements']['mode'] == 'api'
    assert trace['reranking']['mode'] == 'api'
    assert trace['explanations']['mode'] == 'api'
    assert calls[:3] == ['understand', 'rerank', 'explain']



def test_api_is_first_probe_source(monkeypatch):
    from app.main import llm
    from app.core.llm import LLMResult

    calls = []

    async def understand(*args, **kwargs):
        calls.append('understand')
        return LLMResult({'category': None, 'team_size': None, 'integrations': [], 'features': [], 'deployment': [], 'pricing_tier': None, 'confidence': 0.2}, True, False)

    async def generate_probes(*args, **kwargs):
        calls.append('generate_probes')
        return LLMResult({'probes': [{'field': 'category', 'question': 'What type of software do you need?', 'why_it_matters': 'Category determines the candidate set.', 'options': ['CRM', 'Analytics'], 'expected_impact': 1.0}]}, True, False)

    monkeypatch.setattr(llm, 'understand', understand)
    monkeypatch.setattr(llm, 'generate_probes', generate_probes)
    with TestClient(app) as client:
        response = client.post('/api/query', json={'query': 'I need software for my business.'})
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'needs_clarification'
    assert data['trace']['api_trace']['probing']['mode'] == 'api'
    assert calls == ['understand', 'generate_probes']



def test_api_success_does_not_run_deterministic_parser(monkeypatch):
    from app.main import llm
    from app.core.llm import LLMResult

    calls = []

    async def understand(*args, **kwargs):
        calls.append('api')
        return LLMResult({'category': 'CRM', 'team_size': 20, 'integrations': ['Slack'], 'excluded_integrations': [], 'features': [], 'deployment': [], 'pricing_tier': None, 'confidence': 0.9}, True, False)

    def parser(*args, **kwargs):
        calls.append('fallback')
        raise AssertionError('fallback parser must not run after a successful API call')

    monkeypatch.setattr(llm, 'understand', understand)
    monkeypatch.setattr('app.main.parse', parser)
    with TestClient(app) as client:
        response = client.post('/api/query', json={'query': 'CRM for 20 users with Slack', 'top_k': 3})
    assert response.status_code == 200
    assert calls == ['api']



def test_failed_api_invokes_parser_fallback(monkeypatch):
    from app.main import llm
    from app.core.llm import LLMResult
    from app.core.models import CustomerNeeds

    calls = []

    async def understand(*args, **kwargs):
        calls.append('api')
        return LLMResult(None, False, True, 'provider timeout')

    def parser(*args, **kwargs):
        calls.append('fallback')
        return CustomerNeeds(raw_query='CRM for 20 users with Slack', category='CRM', team_size=20, integrations=['Slack'], confidence=0.8)

    monkeypatch.setattr(llm, 'understand', understand)
    monkeypatch.setattr('app.main.parse', parser)
    with TestClient(app) as client:
        response = client.post('/api/query', json={'query': 'CRM for 20 users with Slack', 'top_k': 3})
    assert response.status_code == 200
    assert calls == ['api', 'fallback']



def test_api_negative_integration_is_enforced(monkeypatch):
    from app.main import llm
    from app.core.llm import LLMResult

    async def understand(*args, **kwargs):
        return LLMResult({'category': 'CRM', 'team_size': 20, 'integrations': [], 'excluded_integrations': ['Slack'], 'features': [], 'deployment': [], 'pricing_tier': None, 'confidence': 0.95}, True, False)

    async def explain(*args, **kwargs):
        recs = args[2]
        return LLMResult({'recommendations': [
            {'product_id': r['product_id'], 'why_recommended': [r['product_name']], 'improve_fit': ['Verify plan limits']}
            for r in recs
        ]}, True, False)

    monkeypatch.setattr(llm, 'understand', understand)
    monkeypatch.setattr(llm, 'explain', explain)
    with TestClient(app) as client:
        response = client.post('/api/query', json={'query': 'CRM without Slack', 'top_k': 3})
    assert response.status_code == 200
    data = response.json()
    assert all('slack' not in {i.lower() for i in r['product']['integrations']} for r in data['recommendations'])


def test_react_frontend_contract_is_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'frontend'
    assert (root / 'package.json').exists()
    assert (root / 'vite.config.js').exists()
    app_source = (root / 'src' / 'App.jsx').read_text(encoding='utf-8')
    assert 'useState' in app_source
    assert 'useEffect' in app_source
    assert 'getJSON' in app_source
    assert 'API-first' not in app_source  # policy is enforced by backend, not duplicated in UI


def test_demo_cases_endpoint_uses_relocated_sample_path():
    with TestClient(app) as client:
        response = client.get('/api/demo-cases')
    assert response.status_code == 200
    cases = response.json()
    assert isinstance(cases, list)
    assert len(cases) == 8
    assert cases[0]['label'] == 'CRM + Slack (fully specified)'


def test_root_mounts_vite_asset_prefix_when_frontend_dist_exists():
    from pathlib import Path
    main_source = Path(__file__).resolve().parents[1] / 'app' / 'main.py'
    text = main_source.read_text(encoding='utf-8')
    assert "app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')" in text


def test_vercel_config_does_not_rewrite_static_assets():
    import json
    from pathlib import Path
    config = json.loads((Path(__file__).resolve().parents[2] / 'frontend' / 'vercel.json').read_text(encoding='utf-8'))
    assert config['outputDirectory'] == 'dist'
    assert 'rewrites' not in config


def test_bundled_concrete_demo_queries_have_three_compliant_results():
    import json
    from app.core.data_pipeline import ingest_bytes
    from app.core.query_understanding import parse
    from app.core.ranker import recommend_with_meta
    root = Path(__file__).resolve().parents[2]
    products, _ = ingest_bytes((root / 'sample' / 'messy_catalog.csv').read_bytes(), 'messy_catalog.csv')
    cases = json.loads((root / 'sample' / 'demo_queries.json').read_text(encoding='utf-8'))
    concrete_labels = {
        'CRM + Slack (fully specified)',
        'Project management + Jira + Kanban',
        'Self-hosted analytics (deployment constraint)',
        'Negative integration constraint',
        'Budget-aware HR platform',
        'DevOps + GitHub integration',
        'Helpdesk with ticketing for a small team',
    }
    for case in cases:
        if case['label'] not in concrete_labels:
            continue
        needs = parse(case['query'], case.get('answers', {}))
        recs, _ = recommend_with_meta(products, needs, 3)
        assert len(recs) == 3
        assert all(r.hard_constraints_satisfied for r in recs), case['label']
