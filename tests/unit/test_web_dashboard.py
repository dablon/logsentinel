# tests/unit/test_web_dashboard.py
import pytest
import queue


def test_flask_app_starts_without_error():
    from collectors.web_dashboard import create_app
    app = create_app(queue.Queue())
    assert app is not None
    assert app.debug is False


def test_sse_endpoint_produces_events():
    q = queue.Queue()
    from collectors.web_dashboard import create_app
    app = create_app(q)
    client = app.test_client()
    q.put({'timestamp': '2026-05-19T10:00:00', 'level': 'ERROR', 'source': 'test/pod', 'message': 'fail'})
    response = client.get('/stream')
    assert response.status_code == 200
    assert 'text/event-stream' in response.content_type


def test_status_endpoint():
    q = queue.Queue()
    from collectors.web_dashboard import create_app
    app = create_app(q)
    client = app.test_client()
    response = client.get('/api/status')
    assert response.status_code == 200
    data = response.get_json()
    assert 'namespace' in data
    assert 'level' in data