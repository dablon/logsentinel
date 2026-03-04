#!/usr/bin/env python3
"""Unit tests for LogAnalyzer - NO MOCKS"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from logsentinel import LogAnalyzer, LogEntry

class TestLogAnalyzer:
    def test_analyze_empty(self):
        """Analyze empty log list"""
        analyzer = LogAnalyzer()
        result = analyzer.analyze([])
        
        assert result['summary']['total'] == 0
        assert result['summary']['errors'] == 0
        assert result['summary']['warnings'] == 0
    
    def test_analyze_single_error(self):
        """Analyze single error entry"""
        analyzer = LogAnalyzer()
        entries = [LogEntry(
            timestamp='2026-03-04T10:00:00',
            level='ERROR',
            source='test',
            message='Test error'
        )]
        result = analyzer.analyze(entries)
        
        assert result['summary']['total'] == 1
        assert result['summary']['errors'] == 1
        assert len(result['errors']) == 1
    
    def test_analyze_multiple_errors(self):
        """Analyze multiple error entries"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='ERROR', source='test', message='Error 1'),
            LogEntry(timestamp='2026-03-04T10:00:01', level='ERROR', source='test', message='Error 2'),
            LogEntry(timestamp='2026-03-04T10:00:02', level='INFO', source='test', message='Info'),
        ]
        result = analyzer.analyze(entries)
        
        assert result['summary']['total'] == 3
        assert result['summary']['errors'] == 2
        assert result['summary']['info'] == 1
    
    def test_analyze_warnings(self):
        """Analyze warning entries"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='WARNING', source='test', message='Warning 1'),
            LogEntry(timestamp='2026-03-04T10:00:01', level='WARNING', source='test', message='Warning 2'),
        ]
        result = analyzer.analyze(entries)
        
        assert result['summary']['warnings'] == 2
        assert len(result['warnings']) == 2
    
    def test_analyze_mixed_levels(self):
        """Analyze mixed severity levels"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='DEBUG', source='test', message='Debug'),
            LogEntry(timestamp='2026-03-04T10:00:01', level='INFO', source='test', message='Info'),
            LogEntry(timestamp='2026-03-04T10:00:02', level='WARNING', source='test', message='Warning'),
            LogEntry(timestamp='2026-03-04T10:00:03', level='ERROR', source='test', message='Error'),
            LogEntry(timestamp='2026-03-04T10:00:04', level='CRITICAL', source='test', message='Critical'),
        ]
        result = analyzer.analyze(entries)
        
        assert result['summary']['debug'] == 1
        assert result['summary']['info'] == 1
        assert result['summary']['warnings'] == 1
        assert result['summary']['errors'] == 1
        assert result['summary']['critical'] == 1
    
    def test_analyze_error_limit(self):
        """Errors limited to 50"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='ERROR', source='test', message=f'Error {i}')
            for i in range(100)
        ]
        result = analyzer.analyze(entries)
        
        assert len(result['errors']) == 50  # Limited
    
    def test_analysis_memory_issue(self):
        """Detect memory issues"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='ERROR', source='test', message='Out of memory error'),
            LogEntry(timestamp='2026-03-04T10:00:01', level='ERROR', source='test', message='OOM killed'),
        ]
        result = analyzer.analyze(entries)
        
        recommendations = result['analysis']['recommendations']
        assert any('Memory' in r for r in recommendations)
    
    def test_analysis_connection_issue(self):
        """Detect connection issues"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='ERROR', source='test', message='Connection refused'),
            LogEntry(timestamp='2026-03-04T10:00:01', level='ERROR', source='test', message='Connection timeout'),
        ]
        result = analyzer.analyze(entries)
        
        recommendations = result['analysis']['recommendations']
        assert any('Connection' in r for r in recommendations)
    
    def test_analysis_permission_issue(self):
        """Detect permission issues"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='ERROR', source='test', message='Permission denied'),
        ]
        result = analyzer.analyze(entries)
        
        recommendations = result['analysis']['recommendations']
        assert any('Permission' in r for r in recommendations)
    
    def test_high_error_volume_recommendation(self):
        """Recommend for high error volume"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp=f'2026-03-04T10:00:0{i}', level='ERROR', source='test', message=f'Error {i}')
            for i in range(15)
        ]
        result = analyzer.analyze(entries)
        
        recommendations = result['analysis']['recommendations']
        assert any('High error' in r for r in recommendations)
    
    def test_find_patterns(self):
        """Find common error patterns"""
        analyzer = LogAnalyzer()
        entries = [
            LogEntry(timestamp='2026-03-04T10:00:00', level='ERROR', source='test', message='Database connection failed'),
            LogEntry(timestamp='2026-03-04T10:00:01', level='ERROR', source='test', message='Database connection failed'),
            LogEntry(timestamp='2026-03-04T10:00:02', level='ERROR', source='test', message='Database timeout'),
        ]
        result = analyzer.analyze(entries)
        
        patterns = result['analysis']['error_patterns']
        assert len(patterns) > 0
        # Should find repeated pattern
        assert any(p['count'] >= 2 for p in patterns)
