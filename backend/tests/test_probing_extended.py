"""
test_probing_extended.py — Extended tests for the probing / clarification layer.

These tests verify that:
- the information-gain planner asks the highest-impact questions first
- category is always the first question when no category is resolved
- questions cap at max_questions even with many missing dimensions
- fully-specified requests skip probing entirely
- the probing layer returns useful options for constrained dimensions
"""

from app.core.models import CustomerNeeds, Product
from app.core.query_understanding import probe


def _make_products():
    """Return a heterogeneous catalogue covering multiple categories and dimensions."""
    return [
        Product(id='1', name='FlowCRM',     category='CRM',                integrations=['Slack'],          deployment=['Cloud'],       pricing_tier='$$',  team_size_min=10,  team_size_max=100),
        Product(id='2', name='SalesPilot',  category='CRM',                integrations=['Slack', 'Zapier'],deployment=['SaaS'],        pricing_tier='$$',  team_size_min=5,   team_size_max=250),
        Product(id='3', name='InsightDeck', category='Analytics',          integrations=['Google Drive'],   deployment=['Self-hosted'], pricing_tier='$$$', team_size_min=20,  team_size_max=500),
        Product(id='4', name='TaskForge',   category='Project Management', integrations=['Jira'],           deployment=['Cloud'],       pricing_tier='$$',  team_size_min=5,   team_size_max=500),
        Product(id='5', name='HelpPilot',   category='Helpdesk',           integrations=['Slack', 'Microsoft Teams'], deployment=['SaaS'], pricing_tier='$$', team_size_min=5, team_size_max=250),
    ]


class TestProbeCategoryFirst:
    def test_category_first_when_unresolved(self):
        """When no category is known, category must be the first (and only) question."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need software')
        questions = probe(products, needs, 3)
        assert questions, 'Should produce at least one question'
        assert questions[0][0] == 'category', 'Category must be the first question'

    def test_category_question_provides_options(self):
        """Category question must surface available categories as options."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need software')
        questions = probe(products, needs, 3)
        cats = questions[0][3]  # options list
        assert len(cats) >= 2, 'Category options should include multiple categories'

    def test_only_category_asked_when_unresolved(self):
        """Category is the highest-entropy dimension; no further questions should be asked
        until the category narrows the candidate set."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need software')
        questions = probe(products, needs, 3)
        assert len(questions) == 1
        assert questions[0][0] == 'category'


class TestProbeMissingDimensions:
    def test_no_probe_when_sufficiently_specified(self):
        """A query with category + 3 additional dimensions should skip probing."""
        products = _make_products()
        needs = CustomerNeeds(
            raw_query='CRM for 20 users with Slack and Cloud deployment',
            category='CRM',
            team_size=20,
            integrations=['Slack'],
            deployment=['Cloud'],
        )
        questions = probe(products, needs, 3)
        assert questions == [], 'Fully specified query must not trigger probing'

    def test_probe_asks_about_missing_integration(self):
        """When category is known but integration is missing, probe for integrations."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need a CRM', category='CRM')
        questions = probe(products, needs, 3)
        fields = [q[0] for q in questions]
        assert 'integrations' in fields or 'team_size' in fields or 'deployment' in fields

    def test_max_questions_respected(self):
        """The probe function must never exceed the specified max_questions limit."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need a CRM', category='CRM')
        for limit in (1, 2, 3):
            questions = probe(products, needs, limit)
            assert len(questions) <= limit, f'Expected at most {limit} questions, got {len(questions)}'

    def test_impact_scores_are_sorted_descending(self):
        """Questions must be sorted by expected_impact descending."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need a CRM', category='CRM')
        questions = probe(products, needs, 3)
        if len(questions) >= 2:
            impacts = [q[4] for q in questions]
            assert impacts == sorted(impacts, reverse=True), 'Questions must be sorted by impact descending'

    def test_probe_returns_tuple_format(self):
        """Each returned question must be a 5-tuple: (field, question, why, options, impact)."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need software')
        questions = probe(products, needs, 3)
        for q in questions:
            assert len(q) == 5, f'Expected 5-tuple, got {len(q)}-tuple: {q}'
            field, question, why, options, impact = q
            assert isinstance(field, str) and field
            assert isinstance(question, str) and question
            assert isinstance(why, str) and why
            assert isinstance(options, list)
            assert isinstance(impact, float) and 0.0 <= impact <= 1.0

    def test_no_duplicate_fields_in_probe_output(self):
        """The same dimension should never appear twice in a single probe round."""
        products = _make_products()
        needs = CustomerNeeds(raw_query='I need a CRM', category='CRM')
        questions = probe(products, needs, 5)
        fields = [q[0] for q in questions]
        assert len(fields) == len(set(fields)), 'Duplicate probe fields detected'
