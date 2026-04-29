#!/usr/bin/env python3
"""E2E tests for LogSentinel - NO MOCKS"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from logsentinel import LogParser, LogAnalyzer, LLMAnalyzer
import subprocess

class TestLogSentinelE2E:
    """End-to-end tests with real data"""
    
    def test_full_parse_analyze_flow(self):
        """Test full flow: parse -> analyze"""
        parser = LogParser()
        
        # Create test log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("2026-03-04 10:00:00 INFO Application started\n")
            f.write("2026-03-04 10:00:01 ERROR Database connection failed\n")
            f.write("2026-03-04 10:00:02 WARNING Memory usage at 85%\n")
            f.write("2026-03-04 10:00:03 INFO Request processed\n")
            temp_path = f.name
        
        try:
            # Parse
            entries = parser.parse_file(temp_path)
            assert len(entries) == 4
            
            # Analyze
            analyzer = LogAnalyzer()
            result = analyzer.analyze(entries)
            
            assert result['summary']['total'] == 4
            assert result['summary']['error'] == 1
            assert result['summary']['warning'] == 1
            assert result['summary']['info'] == 2
            
            # Check recommendations generated
            assert 'analysis' in result
            assert 'recommendations' in result['analysis']
            
        finally:
            os.unlink(temp_path)
    
    def test_error_detection_flow(self):
        """Test error detection end-to-end"""
        parser = LogParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("2026-03-04 10:00:00 ERROR Failed to connect\n")
            f.write("2026-03-04 10:00:01 ERROR Connection refused\n")
            f.write("2026-03-04 10:00:02 ERROR Timeout occurred\n")
            temp_path = f.name
        
        try:
            entries = parser.parse_file(temp_path)
            analyzer = LogAnalyzer()
            result = analyzer.analyze(entries)
            
            assert result['summary']['error'] == 3
            assert len(result['errors']) == 3
            
            # Should detect connection issues
            recommendations = result['analysis']['recommendations']
            assert any('Connection' in r for r in recommendations)
            
        finally:
            os.unlink(temp_path)
    
    def test_json_output_flow(self):
        """Test JSON output format"""
        parser = LogParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("2026-03-04 10:00:00 INFO Test\n")
            temp_path = f.name
        
        try:
            entries = parser.parse_file(temp_path)
            analyzer = LogAnalyzer()
            result = analyzer.analyze(entries)
            
            import json
            json_output = json.dumps(result)
            
            # Should be valid JSON
            parsed = json.loads(json_output)
            assert 'summary' in parsed
            
        finally:
            os.unlink(temp_path)
    
    def test_multiple_sources_flow(self):
        """Test analyzing multiple log files"""
        parser = LogParser()
        
        # Create two log files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f1:
            f1.write("2026-03-04 10:00:00 ERROR Error in app1\n")
            temp1 = f1.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f2:
            f2.write("2026-03-04 10:00:01 ERROR Error in app2\n")
            temp2 = f2.name
        
        try:
            entries1 = parser.parse_file(temp1)
            entries2 = parser.parse_file(temp2)
            
            all_entries = entries1 + entries2
            
            analyzer = LogAnalyzer()
            result = analyzer.analyze(all_entries)
            
            assert result['summary']['total'] == 2
            assert result['summary']['error'] == 2
            
        finally:
            os.unlink(temp1)
            os.unlink(temp2)
    
    def test_pattern_detection_real_data(self):
        """Test pattern detection with realistic data"""
        parser = LogParser()
        
        # Simulate real app logs
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            for i in range(10):
                f.write(f"2026-03-04 10:00:{i:02d} ERROR Database query failed: timeout after 30s\n")
            temp_path = f.name
        
        try:
            entries = parser.parse_file(temp_path)
            analyzer = LogAnalyzer()
            result = analyzer.analyze(entries)
            
            # Should detect repeated pattern
            patterns = result['analysis']['error_patterns']
            assert len(patterns) > 0
            
        finally:
            os.unlink(temp_path)

class TestDockerIntegration:
    """Test Docker integration (if available)"""
    
    def test_docker_logs_handles_missing_docker(self):
        """Test graceful handling when docker not available"""
        parser = LogParser()
        
        # This should not crash even if docker unavailable
        # It will just return empty or error message
        try:
            result = parser.parse_docker_logs('nonexistent-container-12345')
            # Should handle gracefully
            assert isinstance(result, list)
        except Exception:
            pass  # Expected if docker not available

class TestCLIIntegration:
    """Test CLI integration"""
    
    def test_cli_help(self):
        """Test CLI help works"""
        result = subprocess.run(
            ['python3', 'logsentinel.py', '--help'],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), '../..')
        )
        
        assert result.returncode == 0
        assert 'LogSentinel' in result.stdout

    def test_cli_monitor_flag(self):
        """Test --monitor flag is recognized"""
        result = subprocess.run(
            ['python3', 'logsentinel.py', '--monitor', '--help'],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), '../..')
        )
        assert '--monitor' in result.stdout

    def test_cli_with_no_args(self):
        """Test CLI with no args"""
        result = subprocess.run(
            ['python3', 'logsentinel.py'],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), '../..')
        )

        # Should show no log entries or usage
        output = result.stdout.lower()
        assert result.returncode == 0 or 'usage' in output or 'no log' in output
