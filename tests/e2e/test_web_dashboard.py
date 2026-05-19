# tests/e2e/test_web_dashboard.py
import pytest
import queue
import threading
import time
from collectors.web_dashboard import create_app


def test_web_dashboard_flow():
    q = queue.Queue(maxsize=100)
    app = create_app(q, namespace='test-ns', level='INFO', filter_keywords=[])

    # Put some items
    q.put({'timestamp': '2026-05-19T10:00:00', 'level': 'ERROR', 'source': 'test-pod', 'message': 'test error'})
    q.put({'timestamp': '2026-05-19T10:00:01', 'level': 'WARNING', 'source': 'test-pod', 'message': 'test warning'})

    client = app.test_client()

    # Check status
    resp = client.get('/api/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['namespace'] == 'test-ns'
    assert data['level'] == 'INFO'
    assert data['running'] is True

    # Check SSE stream
    resp = client.get('/stream')
    assert resp.status_code == 200

    # Check stop endpoint
    resp = client.post('/api/stop')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True


def test_dashboard_route():
    q = queue.Queue()
    app = create_app(q)
    client = app.test_client()
    resp = client.get('/dashboard')
    assert resp.status_code == 200
    assert b'LogSentinel' in resp.data


def test_redirect_root_to_dashboard():
    q = queue.Queue()
    app = create_app(q)
    client = app.test_client()
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/dashboard' in resp.location