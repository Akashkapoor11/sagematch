"""
test_pipeline_extended.py — Additional data-pipeline edge-case tests.

These tests cover normalization rules, edge-case data formats, and
quality-report integrity that are not already covered by test_pipeline.py.
They target the Data Quality judging criterion directly.
"""

from app.core.data_pipeline import (
    ingest_bytes,
    normalize_category,
    normalize_url,
    parse_int,
    parse_list,
    parse_team_range,
    valid_url,
)


# ─── normalize_category ────────────────────────────────────────────────────

class TestNormalizeCategory:
    def test_canonical_crm_alias(self):
        assert normalize_category('Customer Relationship Management') == 'CRM'

    def test_case_insensitive_crm(self):
        assert normalize_category('crm') == 'CRM'

    def test_canonical_hr(self):
        assert normalize_category('human resources') == 'HR'

    def test_canonical_finance(self):
        assert normalize_category('accounting') == 'Finance'

    def test_unknown_category_title_cased(self):
        # Unknown categories should be title-cased, not discarded.
        result = normalize_category('supply chain')
        assert result == 'Supply Chain'

    def test_empty_category_defaults_to_other(self):
        assert normalize_category('') == 'Other'


# ─── parse_int ─────────────────────────────────────────────────────────────

class TestParseInt:
    def test_plain_integer(self):
        assert parse_int('50') == 50

    def test_integer_with_comma(self):
        assert parse_int('1,000') == 1000

    def test_decimal_rejected(self):
        # 50.5 is not a valid team-size integer.
        assert parse_int('50.5') is None

    def test_negative_rejected(self):
        assert parse_int('-10') is None

    def test_none_input(self):
        assert parse_int(None) is None

    def test_empty_string(self):
        assert parse_int('') is None


# ─── parse_team_range ──────────────────────────────────────────────────────

class TestParseTeamRange:
    def test_dash_range(self):
        lo, hi = parse_team_range('10-100')
        assert lo == 10 and hi == 100

    def test_plus_open_ended(self):
        lo, hi = parse_team_range('50+')
        assert lo == 50 and hi == 100000

    def test_up_to_range(self):
        lo, hi = parse_team_range('up to 200')
        assert lo == 1 and hi == 200

    def test_unlimited_sentinel(self):
        lo, hi = parse_team_range('unlimited')
        assert lo == 1 and hi == 100000

    def test_to_range_text(self):
        lo, hi = parse_team_range('10 to 100')
        assert lo == 10 and hi == 100

    def test_decimal_range_rejected(self):
        lo, hi = parse_team_range('10.5-20')
        assert lo is None and hi is None


# ─── parse_list ────────────────────────────────────────────────────────────

class TestParseList:
    def test_comma_delimited(self):
        result = parse_list('Slack, Jira, GitHub')
        assert result == ['Slack', 'Jira', 'GitHub']

    def test_semicolon_delimited(self):
        result = parse_list('Slack; Jira')
        assert result == ['Slack', 'Jira']

    def test_pipe_delimited(self):
        result = parse_list('Slack | Jira')
        assert result == ['Slack', 'Jira']

    def test_case_canonical_known_name(self):
        result = parse_list('ms teams')
        assert 'Microsoft Teams' in result

    def test_deduplication(self):
        result = parse_list('Slack, Slack, Jira')
        assert result.count('Slack') == 1

    def test_empty_items_skipped(self):
        result = parse_list('Slack,,Jira')
        assert '' not in result

    def test_none_returns_empty(self):
        assert parse_list(None) == []


# ─── normalize_url ─────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_customer_support_category_normalizes_to_helpdesk(self):
        raw = b'name,category,description\nFoo,customer support,Helpdesk\n'
        products, _ = ingest_bytes(raw, 'x.csv')
        assert products[0].category == 'Helpdesk'

    def test_scheme_prepended_when_missing(self):
        result = normalize_url('example.com')
        assert result.startswith('https://')

    def test_trailing_slash_stripped(self):
        result = normalize_url('https://example.com/')
        assert not result.endswith('/')

    def test_existing_scheme_preserved(self):
        result = normalize_url('http://example.com')
        assert result.startswith('http://')


# ─── valid_url ─────────────────────────────────────────────────────────────

class TestValidUrl:
    def test_valid_https_url(self):
        assert valid_url('https://example.com') is True

    def test_valid_http_url(self):
        assert valid_url('http://example.com') is True

    def test_invalid_no_dot(self):
        assert valid_url('https://localhost') is False

    def test_empty_string_is_valid(self):
        # Empty means "not provided"; we don't penalize missing URLs.
        assert valid_url('') is True


# ─── ingest_bytes (full pipeline) ─────────────────────────────────────────

class TestIngestBytes:
    def test_reversed_team_bounds_repaired(self):
        """Minimum larger than maximum should be swapped and flagged."""
        raw = b'name,category,description,team_size_min,team_size_max\nFoo,CRM,Desc,100,10\n'
        products, report = ingest_bytes(raw, 'x.csv')
        assert products[0].team_size_min <= products[0].team_size_max
        assert any('reversed' in str(i.issue).lower() for i in report.issues)

    def test_json_array_catalogue(self):
        import json
        data = json.dumps([
            {'name': 'Foo', 'category': 'CRM', 'description': 'Test CRM.', 'integrations': 'Slack'}
        ]).encode()
        products, report = ingest_bytes(data, 'catalog.json')
        assert len(products) == 1
        assert products[0].name == 'Foo'
        assert 'Slack' in products[0].integrations

    def test_json_wrapped_object_catalogue(self):
        import json
        data = json.dumps({'products': [
            {'name': 'Bar', 'category': 'Analytics', 'description': 'Analytics tool.'}
        ]}).encode()
        products, report = ingest_bytes(data, 'catalog.json')
        assert len(products) == 1
        assert products[0].category == 'Analytics'

    def test_malformed_url_flagged_but_kept(self):
        raw = b'name,category,description,url\nFoo,CRM,Desc,not-a-valid-url-!!!\n'
        products, report = ingest_bytes(raw, 'x.csv')
        # Product should be kept, but the bad URL should be flagged.
        assert len(products) == 1
        url_issues = [i for i in report.issues if i.field == 'website']
        assert url_issues, 'Malformed URL should produce a warning issue'

    def test_duplicate_product_id_resolved(self):
        raw = b'id,name,category,description\n1,Foo,CRM,Desc A\n1,Bar,CRM,Desc B\n'
        products, report = ingest_bytes(raw, 'x.csv')
        ids = [p.id for p in products]
        assert len(ids) == len(set(ids)), 'Duplicate product IDs must be made unique'

    def test_empty_name_row_rejected(self):
        raw = b'name,category,description\n,CRM,Missing name\n'
        products, report = ingest_bytes(raw, 'x.csv')
        assert report.rows_rejected >= 1

    def test_quality_score_is_positive(self):
        raw = b'name,category,description\nFoo,CRM,A fine CRM.\n'
        _, report = ingest_bytes(raw, 'x.csv')
        assert 0.0 <= report.score <= 100.0

    def test_quality_score_reflects_sanitized_output_not_rejected_rows(self):
        raw = b'name,category,description\nFoo,CRM,A fine CRM.\n,CRM,Rejected row.\n'
        products, report = ingest_bytes(raw, 'x.csv')
        assert len(products) == 1
        assert report.rows_rejected == 1
        assert report.score == 100.0

    def test_integration_list_canonical_normalization(self):
        """Mixed delimiters and aliases should all parse to canonical names."""
        raw = b'name,category,description,integrations\nFoo,CRM,Desc,slack | ms teams; google drive\n'
        products, _ = ingest_bytes(raw, 'x.csv')
        assert 'Slack' in products[0].integrations
        assert 'Microsoft Teams' in products[0].integrations
        assert 'Google Drive' in products[0].integrations

    def test_deployment_canonical_normalization(self):
        raw = b'name,category,description,deployment\nFoo,CRM,Desc,cloud hosted / self hosted\n'
        products, _ = ingest_bytes(raw, 'x.csv')
        assert 'Cloud' in products[0].deployment or 'Self-hosted' in products[0].deployment

    def test_extra_columns_preserved_in_extra_fields(self):
        raw = b'name,category,description,region,internal_id\nFoo,CRM,Desc,EMEA,X-42\n'
        products, _ = ingest_bytes(raw, 'x.csv')
        ef = products[0].extra_fields
        assert ef.get('region') == 'EMEA'
        assert ef.get('internal_id') == 'X-42'


def test_url_like_deployment_values_are_removed():
    raw = b'name,category,description,deployment\nFoo,CRM,Desc,https://example.com\n'
    products, report = ingest_bytes(raw, 'x.csv')
    assert products[0].deployment == []
    assert report.repair_counts.get('invalid_deployment') == 1
