from app.core.data_pipeline import ingest_bytes

def test_pipeline_normalizes_and_deduplicates():
    raw=b'''Product,Type,Employees,Integrations,Features\nFoo CRM,crm,10-50,Slack | Zapier,Pipeline; Automation\nFoo  CRM,CRM,10 to 50,Slack,Z\n'''
    products, report=ingest_bytes(raw,'x.csv', ['name','category'])
    assert len(products)==1
    assert report.duplicates_removed==1
    assert products[0].team_size_min==10 and products[0].team_size_max==50
    assert 'Slack' in products[0].integrations


def test_team_plus_range_is_open_ended():
    raw=b'''name,category,team_size\nInsight,Analytics,20+\n'''
    products, report=ingest_bytes(raw,'x.csv', ['name','category'])
    assert products[0].team_size_min==20 and products[0].team_size_max==100000


def test_missing_required_field_is_rejected():
    raw=b'name,category\nInsight,Analytics\n'
    try:
        ingest_bytes(raw, 'x.csv', ['name','category','description'])
    except ValueError as exc:
        assert 'description' in str(exc)
    else:
        raise AssertionError('Missing required fields must fail validation')
