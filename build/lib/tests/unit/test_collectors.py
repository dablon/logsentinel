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
