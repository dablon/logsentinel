# collectors/web_dashboard.py
import flask
import queue
import json
import os
import subprocess
import sys

_CLUSTER_FILE = '/tmp/pending_cluster'


def create_app(web_queue: queue.Queue, merger=None, namespace: str = 'unknown',
               level: str = 'INFO', filter_keywords: list = None,
               monitor_ref=None):
    app = flask.Flask(__name__)
    app.debug = False

    state = {
        'namespace': namespace,
        'level': level,
        'filter_keywords': filter_keywords or [],
        'running': True,
        'merger': merger,
        'context': None,
        'monitor_ref': monitor_ref,
    }

    @app.route('/')
    def index():
        return flask.redirect('/dashboard')

    @app.route('/dashboard')
    def dashboard():
        path = os.path.join(os.path.dirname(__file__), 'web_dashboard', 'dashboard.html')
        return flask.send_file(path)

    @app.route('/stream')
    def stream():
        def generate():
            while state['running']:
                try:
                    item = web_queue.get(timeout=1)
                    if item is None:
                        break
                    log_dict = item.to_dict() if hasattr(item, 'to_dict') else item
                    yield f'data: {json.dumps(log_dict)}\n\n'
                except queue.Empty:
                    yield ': ping\n\n'

        return flask.Response(generate(), mimetype='text/event-stream')

    @app.route('/api/status')
    def status():
        return flask.jsonify({
            'namespace': state['namespace'],
            'level': state['level'],
            'filter_keywords': state['filter_keywords'],
            'running': state['running'],
            'context': state.get('context'),
        })

    @app.route('/api/pods')
    def pods():
        merger = state.get('merger')
        if merger:
            pod_list = []
            with merger._pod_lock:
                for pod_key, pod_data in merger.pods.items():
                    pod_list.append({
                        'name': pod_key,
                        'namespace': pod_data.get('namespace', ''),
                    })
            return flask.jsonify({'pods': pod_list})
        return flask.jsonify({'pods': []})

    @app.route('/api/clusters')
    def clusters():
        try:
            result = subprocess.run(
                ['kubectl', 'config', 'get-contexts', '-o', 'name'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                ctxs = [c.strip() for c in result.stdout.strip().split('\n') if c.strip()]
                return flask.jsonify({'contexts': ctxs})
        except Exception:
            pass
        return flask.jsonify({'contexts': []})

    @app.route('/api/clusters/current')
    def cluster_current():
        try:
            result = subprocess.run(
                ['kubectl', 'config', 'current-context'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return flask.jsonify({'context': result.stdout.strip()})
        except Exception:
            pass
        return flask.jsonify({'context': ''})

    @app.route('/api/switch-cluster', methods=['POST'])
    def switch_cluster():
        data = flask.request.get_json() or {}
        new_context = data.get('context', '').strip()
        if new_context:
            try:
                with open(_CLUSTER_FILE, 'w') as f:
                    f.write(new_context)
            except Exception:
                pass
        mon = state.get('monitor_ref')
        if mon:
            try:
                mon._stop_event.set()
                mon.merger.stop()
            except Exception:
                pass
        state['running'] = False
        return flask.jsonify({'switched': True, 'context': new_context})

    @app.route('/api/stop', methods=['POST'])
    def stop():
        state['running'] = False
        return flask.jsonify({'ok': True})

    return app


def start_web_dashboard(web_queue: queue.Queue, port: int = 5050, namespace: str = 'unknown',
                         level: str = 'INFO', filter_keywords: list = None, merger=None,
                         monitor_ref=None):
    app = create_app(web_queue, merger=merger, namespace=namespace, level=level,
                     filter_keywords=filter_keywords, monitor_ref=monitor_ref)
    print(f'Web dashboard started at http://127.0.0.1:{port}')
    app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)