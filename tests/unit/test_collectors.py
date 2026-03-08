"""Unit tests for additional collectors"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

class TestK8sCollector:
    def test_init(self):
        from collectors.k8s_collector import K8sCollector
        c = K8sCollector(namespace="default")
        assert c.namespace == "default"
    
    def test_init_default(self):
        from collectors.k8s_collector import K8sCollector
        c = K8sCollector()
        assert c.namespace is None

class TestSyslogCollector:
    def test_init(self):
        from collectors.k8s_collector import SyslogCollector
        c = SyslogCollector("/var/log/syslog")
        assert c.log_file == "/var/log/syslog"
    
    def test_read_logs_handles_error(self):
        from collectors.k8s_collector import SyslogCollector
        c = SyslogCollector("/nonexistent/file")
        result = c.read_logs(10)
        assert result == []

class TestJournaldCollector:
    def test_init(self):
        from collectors.k8s_collector import JournaldCollector
        c = JournaldCollector("nginx.service")
        assert c.unit == "nginx.service"
    
    def test_get_logs_returns_list(self):
        from collectors.k8s_collector import JournaldCollector
        c = JournaldCollector()
        result = c.get_logs(5)
        assert isinstance(result, list)

class TestPDFGenerator:
    def test_init(self):
        from output.pdf_generator import PDFGenerator
        g = PDFGenerator("/tmp/test_reports")
        assert g.output_dir == "/tmp/test_reports"
    
    def test_create_markdown(self):
        from output.pdf_generator import PDFGenerator
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            g = PDFGenerator(td)
            analysis = {
                'summary': {'total': 100, 'error': 10, 'warning': 5, 'info': 85},
                'errors': [{'level': 'ERROR', 'message': 'Test error'}],
                'warnings': [{'level': 'WARNING', 'message': 'Test warning'}],
                'analysis': {'recommendations': ['Fix errors']}
            }
            md = g._create_markdown(analysis, "Test")
            assert 'Test Report' in md
            assert '100' in md
            assert '10' in md

class TestAlertManager:
    def test_init(self):
        from output.alerts import AlertManager
        m = AlertManager()
        assert len(m.rules) > 0
    
    def test_check_high_errors(self):
        from output.alerts import AlertManager
        m = AlertManager()
        analysis = {'summary': {'error': 15, 'warning': 3}}
        alerts = m.check(analysis)
        assert len(alerts) > 0
        assert any('High error' in a['message'] for a in alerts)
    
    def test_check_no_alerts(self):
        from output.alerts import AlertManager
        m = AlertManager()
        analysis = {'summary': {'error': 1, 'warning': 1}}
        alerts = m.check(analysis)
        assert len(alerts) == 0
    
    def test_check_pattern_alert(self):
        from output.alerts import AlertManager
        m = AlertManager()
        analysis = {
            'summary': {'error': 2, 'warning': 1},
            'analysis': {
                'error_patterns': [
                    {'pattern': 'Database connection failed', 'count': 10}
                ]
            }
        }
        alerts = m.check(analysis)
        assert len(alerts) > 0

class TestNewFunctions:
    def test_get_collector_k8s(self):
        from logsentinel import get_collector
        c = get_collector('k8s', namespace='test')
        assert c is not None
    
    def test_get_collector_invalid(self):
        from logsentinel import get_collector
        c = get_collector('invalid_type')
        assert c is None


class TestK8sNamespaceSmartReading:
    def test_get_namespace_logs_splits_line_budget(self, monkeypatch):
        from collectors.k8s_collector import K8sCollector

        collector = K8sCollector(namespace="payments")
        monkeypatch.setattr(collector, "list_pods", lambda: ["pod-a", "pod-b", "pod-c"])

        calls = []

        def fake_get_pod_logs(pod, container=None, lines=100, previous=False):
            calls.append((pod, lines, previous))
            return [f"{pod}-line"]

        monkeypatch.setattr(collector, "get_pod_logs", fake_get_pod_logs)

        result = collector.get_namespace_logs(lines=10)

        assert set(result.keys()) == {"pod-a", "pod-b", "pod-c"}
        assert all(line_budget == 3 for _, line_budget, _ in calls)
        assert all(previous is False for _, _, previous in calls)

    def test_get_namespace_logs_falls_back_to_previous(self, monkeypatch):
        from collectors.k8s_collector import K8sCollector

        collector = K8sCollector(namespace="payments")
        monkeypatch.setattr(collector, "list_pods", lambda: ["api-pod"])

        def fake_get_pod_logs(pod, container=None, lines=100, previous=False):
            if previous:
                return ["2026-03-04 10:00:00 ERROR restarted pod log"]
            return []

        monkeypatch.setattr(collector, "get_pod_logs", fake_get_pod_logs)

        result = collector.get_namespace_logs(lines=25)

        assert result["api-pod"] == ["2026-03-04 10:00:00 ERROR restarted pod log"]

    def test_parse_k8s_logs_reads_all_pods_in_namespace(self, monkeypatch):
        from logsentinel import LogParser

        class FakeCollector:
            def __init__(self, namespace=None, context=None):
                self.namespace = namespace
                self.context = context

            def get_namespace_logs(self, lines=100, container=None):
                return {
                    "pod-a": ["2026-03-04 10:00:00 ERROR failed"],
                    "pod-b": ["2026-03-04 10:00:01 WARNING slow"],
                }

            def get_pod_logs(self, pod, container=None, lines=100):
                return []

        monkeypatch.setattr("collectors.k8s_collector.K8sCollector", FakeCollector)

        parser = LogParser()
        entries = parser.parse_k8s_logs(namespace="payments", lines=40)

        assert len(entries) == 2
        assert {e.source for e in entries} == {"k8s:payments/pod-a", "k8s:payments/pod-b"}
