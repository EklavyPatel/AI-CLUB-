import httpx
from fastapi.testclient import TestClient
from app import gateway


def test_pooled_gateway_keeps_student_sessions_isolated(monkeypatch):
    monkeypatch.setenv('D1_GATEWAY_URL', 'https://backend.invalid')
    monkeypatch.setenv('D1_GATEWAY_TOKEN', 'gateway-test-secret')
    clients = []
    requests = []
    original = httpx.AsyncClient

    def backend(request):
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer gateway-test-secret'
        if request.url.path == '/api/auth/login':
            return httpx.Response(200, json={'id': 'student-a'}, headers={
                'set-cookie': 'btn_session=student-a-token; HttpOnly; Secure; SameSite=Strict; Path=/'})
        cookie = request.headers.get('cookie', '')
        if cookie == 'btn_session=student-a-token':
            return httpx.Response(200, json={'id': 'student-a', 'role': 'student'})
        if cookie == 'btn_session=student-b-token':
            return httpx.Response(200, json={'id': 'student-b', 'role': 'student'})
        return httpx.Response(401, json={'detail': 'Please sign in to continue.'})

    def factory(**kwargs):
        client = original(transport=httpx.MockTransport(backend), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(gateway.httpx, 'AsyncClient', factory)
    with TestClient(gateway.app, base_url='https://frontend.invalid') as client:
        login = client.post('/api/auth/login', json={'email': 'a@example.com'})
        assert 'HttpOnly' in login.headers['set-cookie']
        assert login.headers['Cache-Control'] == 'no-store'
        assert client.get('/api/auth/me').json()['id'] == 'student-a'
        assert client.get('/api/auth/me', headers={'Cookie': 'btn_session=student-b-token'}).json()['id'] == 'student-b'
        assert client.get('/api/auth/me', headers={'Cookie': ''}).status_code == 401
        assert client.post('/api/question-bank/import-pdf', files={'file': ('q.pdf', b'bad', 'application/pdf')},
                           headers={'Cookie': 'btn_session=student-b-token'}).status_code == 403
        assert len(clients) == 1
        assert list(clients[0].cookies.jar) == []
    assert clients[0].is_closed
