from app.core.models import CustomerNeeds, Product
from app.core.query_understanding import probe

def test_probe_asks_high_impact_missing_dimensions():
    products=[Product(id='1',name='A',category='CRM'),Product(id='2',name='B',category='Analytics')]
    needs=CustomerNeeds(raw_query='I need software')
    qs=probe(products,needs,3)
    assert qs
    assert qs[0][0]=='category'
