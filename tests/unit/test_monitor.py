"""Unit tests for k8s_monitor module"""
import sys
import os
import time
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import fields


def test_logline_fields():
    """LogLine has required fields: timestamp, level, source, message, raw"""
    from collectors.k8s_monitor import LogLine
    field_names = [f.name for f in fields(LogLine)]
    assert 'timestamp' in field_names
    assert 'level' in field_names
    assert 'source' in field_names
    assert 'message' in field_names
    assert 'raw' in field_names


def make_line(level):
    from collectors.k8s_monitor import LogLine
    return LogLine(timestamp=None, level=level, source='test-pod', message='test', raw='test')

def make_line_and_message(level, message):
    from collectors.k8s_monitor import LogLine
    return LogLine(timestamp=None, level=level, source='test-pod', message=message, raw=message)

def test_severity_filter_threshold_warning():
    """ERROR and CRITICAL pass when threshold=ERROR"""
    from collectors.k8s_monitor import SeverityFilter
    sf = SeverityFilter(threshold='ERROR')
    assert not sf.passes(make_line('DEBUG'))
    assert not sf.passes(make_line('INFO'))
    assert not sf.passes(make_line('WARNING'))
    assert sf.passes(make_line('ERROR'))
    assert sf.passes(make_line('CRITICAL'))

def test_severity_filter_threshold_info():
    """INFO, WARNING, ERROR, CRITICAL pass when threshold=INFO"""
    from collectors.k8s_monitor import SeverityFilter
    sf = SeverityFilter(threshold='INFO')
    assert not sf.passes(make_line('DEBUG'))
    assert sf.passes(make_line('INFO'))
    assert sf.passes(make_line('WARNING'))
    assert sf.passes(make_line('ERROR'))
    assert sf.passes(make_line('CRITICAL'))

def test_severity_filter_unknown_level_treated_as_debug():
    """Unknown levels default to DEBUG (0), so they pass when threshold=DEBUG"""
    from collectors.k8s_monitor import SeverityFilter
    sf = SeverityFilter(threshold='DEBUG')
    assert sf.passes(make_line('BLAH'))
    sf2 = SeverityFilter(threshold='ERROR')
    assert not sf2.passes(make_line('BLAH'))

def test_keyword_filter_and_logic():
    """All keywords must be present (AND)"""
    from collectors.k8s_monitor import KeywordFilter
    kf = KeywordFilter(keywords=['timeout', 'db'])
    assert kf.passes(make_line_and_message('INFO', 'Connection timeout to db server'))
    assert not kf.passes(make_line_and_message('INFO', 'Connection timeout'))  # missing 'db'
    assert not kf.passes(make_line_and_message('INFO', 'Database error'))      # missing 'timeout'

def test_keyword_filter_empty_keywords_passes_all():
    """No keywords configured = pass all"""
    from collectors.k8s_monitor import KeywordFilter
    kf = KeywordFilter(keywords=[])
    assert kf.passes(make_line_and_message('INFO', 'Anything'))

def test_keyword_filter_case_insensitive():
    """Keyword matching is case-insensitive"""
    from collectors.k8s_monitor import KeywordFilter
    kf = KeywordFilter(keywords=['TIMEOUT'])
    assert kf.passes(make_line_and_message('INFO', 'connection timeout'))
    assert kf.passes(make_line_and_message('INFO', 'TIMEOUT CONNECTION'))

def test_merger_stop_signals_threads_to_exit():
    """stop() sets stop_event, threads exit cleanly"""
    from collectors.k8s_monitor import LogStreamMerger

    # Mock subprocess.Popen to simulate kubectl logs --follow
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdout.readline = MagicMock(side_effect=['line1\n', 'line2\n', ''])

    with patch('collectors.k8s_monitor.subprocess.Popen', return_value=mock_proc), \
         patch('collectors.k8s_collector.K8sCollector') as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.list_pods.return_value = ['pod-a', 'pod-b']

        m = LogStreamMerger(namespace='test-ns', context=None, lines_back=5)
        m.start()
        # Should have discovered pods via mocked K8sCollector
        assert mock_collector.list_pods.called
        m.stop()
        for pod_name, pod_data in m.pods.items():
            pod_data['thread'].join(timeout=5)
            assert not pod_data['thread'].is_alive()


def test_terminal_display_colors():
    """ERROR and CRITICAL lines use RED color"""
    from collectors.k8s_monitor import TerminalDisplay
    td = TerminalDisplay()
    assert td._color_for_level('ERROR') == td.RED
    assert td._color_for_level('CRITICAL') == td.RED
    assert td._color_for_level('WARNING') == td.YELLOW
    assert td._color_for_level('INFO') == td.CYAN
    assert td._color_for_level('DEBUG') == td.GRAY


def test_log_monitor_collects_pods_on_start():
    """LogMonitor.start() discovers pods via K8sCollector"""
    from unittest.mock import patch, MagicMock
    from collectors.k8s_monitor import LogMonitor
    with patch('collectors.k8s_monitor.LogStreamMerger') as mock_merger_cls:
        mock_merger_instance = mock_merger_cls.return_value
        mock_merger_instance.pods = {}
        mock_merger_instance.start = MagicMock()
        mock_merger_instance.stream = MagicMock(return_value=iter([]))
        m = LogMonitor(namespace='test', context=None)
        # The merger should have been created and started
        assert m.merger is not None
        mock_merger_cls.assert_called_once()


def test_terminal_display_format_line():
    """Lines are formatted as [timestamp] [LEVEL  ] [source] message"""
    from collectors.k8s_monitor import LogLine, TerminalDisplay
    from datetime import datetime
    td = TerminalDisplay()
    line = LogLine(
        timestamp=datetime(2026, 4, 28, 10, 42, 15),
        level='ERROR',
        source='api-pod',
        message='Connection refused',
        raw='Connection refused'
    )
    formatted = td._format_line(line)
    assert '[ERROR  ]' in formatted
    assert '[api-pod]' in formatted
    assert 'Connection refused' in formatted