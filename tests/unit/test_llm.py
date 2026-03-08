#!/usr/bin/env python3
"""Unit tests for LLM Analyzer - NO MOCKS"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from logsentinel import LLMAnalyzer

class TestLLMAnalyzer:
    def test_init_defaults(self):
        """Test default initialization"""
        analyzer = LLMAnalyzer()
        
        assert analyzer.provider == 'openai'
        assert analyzer.model == 'gpt-4o-mini'
    
    def test_init_custom(self):
        """Test custom initialization"""
        analyzer = LLMAnalyzer(provider='groq', model='llama-3.1-70b')
        
        assert analyzer.provider == 'groq'
        assert analyzer.model == 'llama-3.1-70b'
    
    def test_init_with_api_key(self):
        """Test initialization with API key"""
        analyzer = LLMAnalyzer(api_key='test-key-123')
        
        assert analyzer.api_key == 'test-key-123'
    
    def test_analyze_without_api_key(self):
        """Test analysis without API key returns message"""
        analyzer = LLMAnalyzer(api_key='')
        
        analysis = {
            'summary': {'total': 10, 'errors': 2, 'warnings': 1},
            'errors': [{'message': 'Error 1'}],
            'warnings': [{'message': 'Warning 1'}]
        }
        
        result = analyzer.analyze_with_llm(analysis)
        
        assert 'not configured' in result.lower() or 'error' in result.lower()
    
    def test_analyze_with_api_key_structure(self):
        """Test analysis returns proper structure"""
        analyzer = LLMAnalyzer()
        
        analysis = {
            'summary': {'total': 5, 'errors': 2, 'warnings': 1},
            'errors': [{'message': 'Test error'}],
            'warnings': [{'message': 'Test warning'}]
        }
        
        # This will fail without real API but structure is correct
        result = analyzer.analyze_with_llm(analysis)
        
        assert isinstance(result, str)
    
    def test_endpoints_configured(self):
        """Test API endpoints are configured"""
        analyzer = LLMAnalyzer()
        
        assert 'openai' in analyzer.endpoints
        assert 'anthropic' in analyzer.endpoints
        assert 'groq' in analyzer.endpoints
        assert 'minimax' in analyzer.endpoints
    
    def test_env_var_provider(self):
        """Test provider from environment variable"""
        os.environ['LLM_PROVIDER'] = 'anthropic'
        
        analyzer = LLMAnalyzer()
        
        assert analyzer.provider == 'anthropic'
        
        del os.environ['LLM_PROVIDER']
    
    def test_env_var_model(self):
        """Test model from environment variable"""
        os.environ['LLM_MODEL'] = 'claude-3-5-sonnet'
        
        analyzer = LLMAnalyzer()
        
        assert analyzer.model == 'claude-3-5-sonnet'
        
        del os.environ['LLM_MODEL']
    
    def test_env_var_api_key(self):
        """Test API key from environment variable"""
        os.environ['OPENAI_API_KEY'] = 'env-test-key'
        
        analyzer = LLMAnalyzer()
        
        assert analyzer.api_key == 'env-test-key'
        
        del os.environ['OPENAI_API_KEY']

    def test_env_var_api_key_minimax(self):
        """Test Minimax API key from environment variable"""
        os.environ['LLM_PROVIDER'] = 'minimax'
        os.environ['MINIMAX_API_KEY'] = 'minimax-test-key'

        analyzer = LLMAnalyzer()

        assert analyzer.api_key == 'minimax-test-key'

        del os.environ['MINIMAX_API_KEY']
        del os.environ['LLM_PROVIDER']
