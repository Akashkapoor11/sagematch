from app.core.data_pipeline import ingest_bytes
from app.core.models import CustomerNeeds, Product
from app.core.query_understanding import parse, probe
from app.core.ranker import recommend


def test_negative_requirement_penalizes_forbidden_integration():
    products = [
        Product(id='1', name='A', category='CRM', integrations=['Slack'], team_size_min=1, team_size_max=100),
        Product(id='2', name='B', category='CRM', integrations=['Zoom'], team_size_min=1, team_size_max=100),
    ]
    needs = CustomerNeeds(raw_query='CRM without Slack', category='CRM', excluded_integrations=['Slack'])
    recs = recommend(products, needs, 2)
    assert recs[0].product.name == 'B'
    assert recs[0].hard_constraints_satisfied


def test_hard_constraints_are_relaxed_only_when_insufficient():
    products = [
        Product(id='1', name='SlackCRM', category='CRM', integrations=['Slack'], team_size_min=1, team_size_max=100),
        Product(id='2', name='ZoomCRM', category='CRM', integrations=['Zoom'], team_size_min=1, team_size_max=100),
        Product(id='3', name='SlackPM', category='Project Management', integrations=['Slack'], team_size_min=1, team_size_max=100),
    ]
    needs = CustomerNeeds(raw_query='CRM with Slack', category='CRM', integrations=['Slack'])
    recs = recommend(products, needs, 3)
    assert recs[0].product.name == 'SlackCRM'
    assert any(not r.hard_constraints_satisfied for r in recs[1:])


def test_feature_synonyms_are_extracted():
    needs = parse('I need analytics dashboards and reporting for 40 users')
    assert needs.category == 'Analytics'
    assert needs.team_size == 40
    assert 'dashboards' in needs.features
    assert 'reporting' in needs.features


def test_probing_uses_available_variation():
    products = [
        Product(id='1', name='A', category='CRM', integrations=['Slack'], deployment=['Cloud'], pricing_tier='$'),
        Product(id='2', name='B', category='CRM', integrations=['Jira'], deployment=['Self-hosted'], pricing_tier='$$$'),
        Product(id='3', name='C', category='CRM', integrations=['Slack'], deployment=['Hybrid'], pricing_tier='$$'),
    ]
    needs = CustomerNeeds(raw_query='I need CRM', category='CRM')
    questions = probe(products, needs, 3)
    assert questions
    assert questions[0][0] in {'integrations', 'deployment', 'pricing_tier'}


def test_unknown_columns_are_preserved():
    raw = b'''name,category,description,owner_region,internal_score\nFoo,CRM,Example product,APAC,7\n'''
    products, _ = ingest_bytes(raw, 'catalog.csv')
    assert products[0].extra_fields['owner_region'] == 'APAC'
    assert products[0].extra_fields['internal_score'] == '7'
