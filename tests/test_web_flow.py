from app.settings import TITLE


def test_page_and_stages(client):
    page = client.get('/')
    assert page.status_code == 200 and TITLE in page.text
    for route,field in [('intake','encoding'),('contract','accepted'),('quality','ready'),('domain','accepted'),('reconcile','balanced')]:
        response = client.post(f'/api/{route}',json={})
        assert response.status_code == 200 and field in response.json()


def test_malformed_sample_can_retry(client):
    invalid = client.post('/api/runs',json={'data':'"ab'})
    assert invalid.json()['code']=='CSV'
    assert client.post('/api/runs',json={}).json()['counts']['accepted']==26


def test_accepted_single_source_has_external_diff(client):
    report = client.post('/api/reconcile',json={}).json()
    assert report['balanced'] and report['book']['mismatched']==3


def test_compare_tab_and_static_assets_available(client):
    page = client.get('/').text
    assert '批次并排对账' in page and 'compare-panel' in page
    assert client.get('/static/workspace.js').status_code == 200
    run_id = client.post('/api/runs', json={}).json()['manifest']['run_id']
    listing = client.get('/api/runs').json()
    assert len(listing) == 1 and listing[0]['id'] == run_id
    # 页面初始即可打开对账模块，不要求先跑新输入。
    assert client.get('/api/compare').json() == []
