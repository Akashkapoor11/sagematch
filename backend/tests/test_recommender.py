from app.core.models import CustomerNeeds, Product
from app.core.ranker import recommend, recommend_with_meta

def test_required_integration_affects_rank():
    p1=Product(id='1',name='A',category='CRM',integrations=['Slack'],features=['pipeline'],team_size_min=1,team_size_max=100)
    p2=Product(id='2',name='B',category='CRM',integrations=['Zoom'],features=['pipeline'],team_size_min=1,team_size_max=100)
    n=CustomerNeeds(raw_query='CRM for 20 users with Slack',category='CRM',team_size=20,integrations=['Slack'])
    recs=recommend([p2,p1],n,3)
    assert recs[0].product.name=='A'

def test_top_three_stay_in_category_when_catalog_has_three_matches():
    products=[
        Product(id='1',name='A',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
        Product(id='2',name='B',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
        Product(id='3',name='C',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
        Product(id='4',name='D',category='Design',integrations=['Slack'],team_size_min=1,team_size_max=100),
    ]
    n=CustomerNeeds(raw_query='CRM for 20 users with Slack',category='CRM',team_size=20,integrations=['Slack'])
    recs=recommend(products,n,3)
    assert len(recs)==3
    assert all(r.product.category=='CRM' for r in recs)

def test_top_three_stay_in_category_for_analytics_demo():
    products=[
        Product(id='1',name='A',category='Analytics',integrations=['Slack'],features=['dashboards'],deployment=['Self-hosted'],team_size_min=1,team_size_max=100),
        Product(id='2',name='B',category='Analytics',integrations=['Slack'],features=['dashboards'],deployment=['Cloud'],team_size_min=1,team_size_max=1000),
        Product(id='3',name='C',category='Analytics',integrations=['Google Workspace'],features=['reporting'],deployment=['Cloud'],team_size_min=1,team_size_max=5000),
        Product(id='4',name='D',category='Finance',integrations=['Slack'],features=['dashboards'],deployment=['Cloud'],team_size_min=1,team_size_max=100),
    ]
    n=CustomerNeeds(raw_query='self-hosted analytics with dashboards for 50 users',category='Analytics',team_size=50,deployment=['Self-hosted'],features=['dashboards'])
    recs=recommend(products,n,3)
    assert all(r.product.category=='Analytics' for r in recs)


def test_candidate_pool_can_expose_more_than_top_k_for_api_reranking():
    products=[
        Product(id='1',name='A',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
        Product(id='2',name='B',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
        Product(id='3',name='C',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
        Product(id='4',name='D',category='CRM',integrations=['Slack'],team_size_min=1,team_size_max=100),
    ]
    n=CustomerNeeds(raw_query='CRM for 20 users with Slack',category='CRM',team_size=20,integrations=['Slack'])
    recs, meta = recommend_with_meta(products,n,3,candidate_pool_size=4)
    assert len(recs) == 4
    assert meta['strict_pool_size'] == 4
