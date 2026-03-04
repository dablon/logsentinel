#!/usr/bin/env python3
"""Unit tests for LogParser - NO MOCKS"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from logsentinel import LogParser, LogEntry

class TestLogParser:
    def test_parse_line_standard_format(self):
        """Parse standard timestamp + level format"""
        parser = LogParser()
        line = "2026-03-04 10:00:00 ERROR Database connection failed"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'ERROR'
        assert 'Database' in entry.message
        assert entry.source == 'test'
    
    def test_parse_line_iso_format(self):
        """Parse ISO timestamp format"""
        parser = LogParser()
        line = "2026-03-04T10:00:00Z INFO Application started"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'INFO'
        assert 'Application' in entry.message
    
    def test_parse_line_warning(self):
        """Parse WARNING level"""
        parser = LogParser()
        line = "2026-03-04 10:00:00 WARNING Memory usage high"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'WARNING'
    
    def test_parse_line_debug(self):
        """Parse DEBUG level"""
        parser = LogParser()
        line = "2026-03-04 10:00:00 DEBUG Processing request"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'DEBUG'
    
    def test_parse_line_critical(self):
        """Parse CRITICAL level"""
        parser = LogParser()
        line = "2026-03-04 10:00:00 CRITICAL System failure"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'CRITICAL'
    
    def test_parse_line_fatal(self):
        """Parse FATAL level"""
        parser = LogParser()
        line = "2026-03-04 10:00:00 FATAL Process crashed"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'FATAL'
    
    def test_parse_line_case_insensitive(self):
        """Parse level regardless of case"""
        parser = LogParser()
        
        line1 = "2026-03-04 10:00:00 error Database failed"
        entry1 = parser.parse_line(line1, 'test')
        assert entry1.level == 'ERROR'
        
        line2 = "2026-03-04 10:00:00 Error Database failed"
        entry2 = parser.parse_line(line2, 'test')
        assert entry2.level == 'ERROR'
    
    def test_parse_line_no_timestamp(self):
        """Parse line without timestamp"""
        parser = LogParser()
        line = "This is a plain log message"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'INFO'
        assert entry.message == line
    
    def test_parse_line_error_in_message(self):
        """Detect error in message without level"""
        parser = LogParser()
        line = "Connection error occurred"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'ERROR'
    
    def test_parse_line_warning_in_message(self):
        """Detect warning in message"""
        parser = LogParser()
        line = "Low memory warning"
        entry = parser.parse_line(line, 'test')
        
        assert entry is not None
        assert entry.level == 'WARNING'
    
    def test_parse_line_empty(self):
        """Handle empty line"""
        parser = LogParser()
        entry = parser.parse_line("", 'test')
        assert entry is None
    
    def test_parse_line_whitespace_only(self):
        """Handle whitespace only"""
        parser = LogParser()
        entry = parser.parse_line("   \t  ", 'test')
        assert entry is None

class TestLogParserFile:
    def test_parse_file(self):
        """Parse log file"""
        parser = LogParser()
        
        # Create temp file with logs
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("2026-03-04 10:00:00 INFO Starting\n")
            f.write("2026-03-04 10:00:01 ERROR Failed\n")
            f.write("2026-03-04 10:00:02 WARNING Warning\n")
            f.write("2026-03-04 10:00:03 INFO Done\n")
            temp_path = f.name
        
        try:
            entries = parser.parse_file(temp_path)
            assert len(entries) == 4
            assert entries[0].level == 'INFO'
            assert entries[1].level == 'ERROR'
            assert entries[2].level == 'WARNING'
        finally:
            os.unlink(temp_path)
    
    def test_parse_file_not_found(self):
        """Handle missing file"""
        parser = LogParser()
        entries = parser.parse_file('/nonexistent/file.log')
        assert len(entries) == 0
    
    def test_parse_file_with_utf8(self):
        """Handle UTF-8 content"""
        parser = LogParser()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
            f.write("2026-03-04 10:00:00 INFO Unicode: café, naïve\n")
            temp_path = f.name
        
        try:
            entries = parser.parse_file(temp_path)
            assert len(entries) == 1
            assert 'café' in entries[0].message
        finally:
            os.unlink(temp_path)

class TestLogEntry:
    def test_to_dict(self):
        """Convert entry to dict"""
        entry = LogEntry(
            timestamp='2026-03-04T10:00:00',
            level='ERROR',
            source='test',
            message='Test message'
        )
        d = entry.to_dict()
        
        assert d['timestamp'] == '2026-03-04T10:00:00'
        assert d['level'] == 'ERROR'
        assert d['source'] == 'test'
        assert d['message'] == 'Test message'
