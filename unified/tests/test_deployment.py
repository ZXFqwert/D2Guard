import sys
from pathlib import Path
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment.runtime import create_host


def test_prefixed_web_contract_and_readonly(client, tmp_path):
    (tmp_path / 'index.html').write_text('<h1>D2Guard</h1>')
    app = create_host(client.app, tmp_path, '/safe/desk', True)
    with TestClient(app) as web:
        assert web.get('/safe/desk').url.path == '/safe/desk/'
        assert web.get('/safe/desk/').status_code == 200
        assert web.get('/safe/desk/healthz').json()['mode'] == 'web'
        assert '/api/v1/actions/decide' in web.get('/safe/desk/openapi.json').json()['paths']
        assert web.get('/safe/desk/api/desktop/models/config').status_code == 200
        assert web.post('/safe/desk/api/desktop/models/config', json={}).status_code == 403
        assert web.post('/safe/desk/api/desktop/models/test', json={}).status_code == 403
        assert web.get('/api/desktop/models/config').status_code == 404
        assert web.get('/safe/desk/api/desktop/policies', headers={'Origin': 'https://evil.example'}).status_code == 403


def test_desktop_single_origin_model_config(client, tmp_path):
    (tmp_path / 'index.html').write_text('desktop')
    with TestClient(create_host(client.app, tmp_path, '', False), base_url='http://127.0.0.1:8765') as desk:
        assert desk.get('/').status_code == 200
        r = desk.post('/api/desktop/models/config', json={'main_model': 'test'}, headers={'Origin': 'http://127.0.0.1:8765'})
        assert r.status_code == 200
        assert r.json()['main_model'] == 'test'
