"""
test_ranker_extended.py — Extended recommendation-ranking tests.

Covers scoring correctness, hard-constraint enforcement, strict/relaxed pool
behaviour, exclusion penalties, semantic similarity, and the match_summary
format — all targeting the Recommendation Logic and Reasoning judging criteria.
"""

from app.core.models import CustomerNeeds, Product
from app.core.ranker import (
    recommend,
    recommend_with_meta,
    score_product,
    team_match,
    list_match,
    corpus_idf,
)


def _crm_products():
    return [
        Product(id='c1', name='FlowCRM',    category='CRM', integrations=['Slack', 'Zapier'],
                features=['pipeline', 'automation'], deployment=['Cloud'], pricing_tier='$$',
                team_size_min=1, team_size_max=100, description='Sales CRM with pipeline.'),
        Product(id='c2', name='SalesPilot', category='CRM', integrations=['Slack', 'Google Workspace'],
                features=['lead management', 'analytics'], deployment=['Cloud'], pricing_tier='$$',
                team_size_min=5, team_size_max=250, description='Lead-routing CRM.'),
        Product(id='c3', name='DealFlow',   category='CRM', integrations=['Slack', 'Zoom'],
                features=['pipeline', 'forecasting'], deployment=['SaaS'], pricing_tier='$$$',
                team_size_min=10, team_size_max=500, description='Forecasting-focused CRM.'),
        Product(id='p1', name='TaskForge',  category='Project Management', integrations=['Jira'],
                features=['kanban', 'workflow'], deployment=['Cloud'], pricing_tier='$$',
                team_size_min=5, team_size_max=500, description='Flexible PM tool.'),
    ]


# ─── team_match ────────────────────────────────────────────────────────────

class TestTeamMatch:
    def test_exact_within_range(self):
        p = Product(id='1', name='A', category='CRM', team_size_min=10, team_size_max=100)
        score, msg, ok = team_match(50, p)
        assert ok is True
        assert score == 1.0

    def test_below_minimum_fails(self):
        p = Product(id='1', name='A', category='CRM', team_size_min=100, team_size_max=500)
        score, msg, ok = team_match(5, p)
        assert ok is False
        assert score == 0.0

    def test_above_maximum_fails(self):
        p = Product(id='1', name='A', category='CRM', team_size_min=1, team_size_max=50)
        score, msg, ok = team_match(100, p)
        assert ok is False

    def test_no_team_size_product_returns_neutral(self):
        p = Product(id='1', name='A', category='CRM')
        score, msg, ok = team_match(30, p)
        # No catalog range → neutral, not a hard failure
        assert score == 0.45
        assert ok is False

    def test_no_requirement_returns_neutral(self):
        p = Product(id='1', name='A', category='CRM', team_size_min=1, team_size_max=100)
        score, msg, ok = team_match(None, p)
        assert score == 0.5


# ─── list_match ─────────────────────────────────────────────────────────────

class TestListMatch:
    def test_full_match(self):
        score, matched, missing = list_match(['Slack', 'Jira'], ['Slack', 'Jira', 'GitHub'])
        assert score == 1.0
        assert missing == []

    def test_partial_match(self):
        score, matched, missing = list_match(['Slack', 'Jira'], ['Slack'])
        assert score == 0.5
        assert 'Jira' in missing

    def test_no_match(self):
        score, matched, missing = list_match(['Zoom'], ['Slack', 'Jira'])
        assert score == 0.0
        assert 'Zoom' in missing

    def test_empty_required_returns_neutral(self):
        score, matched, missing = list_match([], ['Slack', 'Jira'])
        assert score == 0.5

    def test_case_insensitive_match(self):
        score, _, _ = list_match(['slack'], ['Slack'])
        assert score == 1.0


# ─── score_product ──────────────────────────────────────────────────────────

class TestScoreProduct:
    def test_perfect_match_score_near_one(self):
        p = Product(id='1', name='FlowCRM', category='CRM', integrations=['Slack'],
                    deployment=['Cloud'], team_size_min=1, team_size_max=100, description='Sales CRM.')
        n = CustomerNeeds(raw_query='CRM for 20 users with Slack on Cloud',
                          category='CRM', team_size=20, integrations=['Slack'], deployment=['Cloud'])
        score, _, _, hard, _, _ = score_product(p, n, corpus_idf([p]))
        assert score >= 0.7
        assert 'category' not in hard
        assert 'integrations' not in hard
        assert 'team_size' not in hard

    def test_wrong_category_is_hard_failure(self):
        p = Product(id='1', name='A', category='Analytics')
        n = CustomerNeeds(raw_query='CRM please', category='CRM')
        score, _, _, hard, _, _ = score_product(p, n)
        assert 'category' in hard
        # Score should be severely penalized
        assert score < 0.3

    def test_excluded_integration_penalized(self):
        p = Product(id='1', name='A', category='CRM', integrations=['Slack'])
        n = CustomerNeeds(raw_query='CRM without Slack', category='CRM', excluded_integrations=['Slack'])
        score, _, _, hard, _, _ = score_product(p, n)
        assert 'excluded_integration' in hard
        assert score < 0.15  # 0.08x multiplier

    def test_match_summary_contains_score(self):
        p = Product(id='1', name='A', category='CRM', integrations=['Slack'],
                    team_size_min=1, team_size_max=100, description='CRM.')
        n = CustomerNeeds(raw_query='CRM', category='CRM')
        from app.core.ranker import recommend_with_meta
        recs, _ = recommend_with_meta([p], n, 1)
        assert '/100' in recs[0].match_summary or '%' in recs[0].match_summary


# ─── recommend_with_meta ────────────────────────────────────────────────────

class TestRecommendWithMeta:
    def test_strict_pool_filled_from_compliant_candidates(self):
        products = _crm_products()
        needs = CustomerNeeds(raw_query='CRM for 20 users with Slack',
                              category='CRM', team_size=20, integrations=['Slack'])
        recs, meta = recommend_with_meta(products, needs, 3)
        assert len(recs) == 3
        # All CRM products with Slack in range should be strictly compliant
        assert meta['strict_pool_size'] >= 3
        assert all(r.hard_constraints_satisfied for r in recs)

    def test_wrong_category_candidates_excluded_when_enough_compliant(self):
        products = _crm_products()
        needs = CustomerNeeds(raw_query='CRM with Slack',
                              category='CRM', integrations=['Slack'])
        recs, _ = recommend_with_meta(products, needs, 3)
        categories = {r.product.category for r in recs}
        # No non-CRM product should appear when at least 3 CRM products satisfy constraints.
        assert 'Project Management' not in categories

    def test_relaxed_candidates_appear_when_strict_pool_insufficient(self):
        """When fewer than top_k products satisfy hard constraints, relaxed candidates fill in."""
        products = [
            Product(id='1', name='Only', category='CRM', integrations=['Slack'],
                    team_size_min=1, team_size_max=100, description='CRM.'),
            Product(id='2', name='Zoom-only', category='CRM', integrations=['Zoom'],
                    team_size_min=1, team_size_max=100, description='CRM.'),
            Product(id='3', name='No-match', category='Analytics', integrations=['Jira'],
                    team_size_min=1, team_size_max=100, description='Analytics.'),
        ]
        needs = CustomerNeeds(raw_query='CRM with Slack',
                              category='CRM', integrations=['Slack'])
        recs, meta = recommend_with_meta(products, needs, 3)
        assert meta['relaxed_constraints'] is True
        # Strict candidates must still lead.
        assert recs[0].hard_constraints_satisfied

    def test_excluded_integration_never_ranks_first_over_clean_candidate(self):
        products = [
            Product(id='1', name='WithSlack',    category='CRM', integrations=['Slack'],
                    team_size_min=1, team_size_max=100),
            Product(id='2', name='WithoutSlack', category='CRM', integrations=['Zoom'],
                    team_size_min=1, team_size_max=100),
        ]
        needs = CustomerNeeds(raw_query='CRM without Slack', category='CRM',
                              excluded_integrations=['Slack'])
        recs = recommend(products, needs, 2)
        assert recs[0].product.name == 'WithoutSlack'

    def test_recommendations_have_evidence(self):
        """Every recommendation must carry at least one evidence item."""
        products = _crm_products()
        needs = CustomerNeeds(raw_query='CRM with Slack', category='CRM', integrations=['Slack'])
        recs = recommend(products, needs, 3)
        for r in recs:
            assert r.evidence, f'{r.product.name} has no evidence items'

    def test_recommendations_ranked_consecutively(self):
        products = _crm_products()
        needs = CustomerNeeds(raw_query='CRM', category='CRM')
        recs = recommend(products, needs, 3)
        ranks = [r.rank for r in recs]
        assert ranks == list(range(1, len(recs) + 1))

    def test_score_breakdown_keys_present(self):
        products = _crm_products()
        needs = CustomerNeeds(raw_query='CRM with Slack for 20 users',
                              category='CRM', team_size=20, integrations=['Slack'])
        recs = recommend(products, needs, 1)
        breakdown = recs[0].score_breakdown
        assert 'category' in breakdown
        assert 'integrations' in breakdown
        assert 'team_size' in breakdown
        assert 'semantic' in breakdown


def test_evidence_preserves_product_source_row():
    from app.core.models import CustomerNeeds, Product
    from app.core.ranker import score_product
    product = Product(id='p1', name='FlowCRM', category='CRM', description='Sales CRM.', integrations=['Slack'], team_size_min=1, team_size_max=100, source_row=42)
    needs = CustomerNeeds(raw_query='CRM for 20 users with Slack', category='CRM', team_size=20, integrations=['Slack'])
    _, _, _, _, evidence, _ = score_product(product, needs)
    assert evidence
    assert all(item.source_row == 42 for item in evidence)
