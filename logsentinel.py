#!/usr/bin/env python3
"""
LogSentinel - AI-Powered Log Analyzer
Analyzes logs from multiple sources using LLM to detect anomalies and provide insights.
"""
import os
import re
import json
import argparse
import sys
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import subprocess

@dataclass
class LogEntry:
    timestamp: str
    level: str
    source: str
    message: str
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp,
            'level': self.level,
            'source': self.source,
            'message': self.message
        }

class LogParser:
    """Parse logs from various sources"""
    
    LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL']
    
    def parse_line(self, line: str, source: str = 'unknown') -> Optional[LogEntry]:
        line = line.strip()
        if not line:
            return None
        
        # Try common log formats
        # Format: 2026-03-04 10:00:00 ERROR message
        match = re.match(r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[Z]?)\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL|FATAL)\s+(.+)', line, re.IGNORECASE)
        if match:
            return LogEntry(
                timestamp=match.group(1),
                level=match.group(2).upper(),
                source=source,
                message=match.group(3)
            )
        
        # Try syslog format
        # Format: Mar  4 10:00:00 hostname process[pid]: message
        match = re.match(r'(\w+\s+\d+\s+\d{2}:\d{2}:\d{2})\s+\S+\s+\S+\[?\d*\]?:\s*(.+)', line)
        if match:
            level = 'INFO'
            if 'error' in line.lower():
                level = 'ERROR'
            elif 'warning' in line.lower():
                level = 'WARNING'
            elif 'critical' in line.lower():
                level = 'CRITICAL'
            return LogEntry(
                timestamp=datetime.now().isoformat(),
                level=level,
                source=source,
                message=match.group(2)
            )
        
        # Fallback: treat whole line as message
        level = 'INFO'
        lower_line = line.lower()
        for lvl in self.LEVELS:
            if lvl.lower() in lower_line:
                level = lvl
                break
        
        return LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            source=source,
            message=line[:500]  # Truncate long lines
        )
    
    def parse_file(self, filepath: str) -> List[LogEntry]:
        entries = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    entry = self.parse_line(line, source=filepath)
                    if entry:
                        entries.append(entry)
        except FileNotFoundError:
            print(f"Error: File not found: {filepath}")
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
        return entries
    
    def parse_docker_logs(self, container: str, lines: int = 100) -> List[LogEntry]:
        """Get logs from docker container"""
        entries = []
        try:
            result = subprocess.run(
                ['docker', 'logs', '--tail', str(lines), container],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30
            )
            if result.stdout:
                for line in result.stdout.split('\n'):
                    entry = self.parse_line(line, source=f'docker:{container}')
                    if entry:
                        entries.append(entry)
        except subprocess.TimeoutExpired:
            print(f"Timeout getting logs from {container}")
        except FileNotFoundError:
            print("Docker not available")
        except Exception as e:
            print(f"Error getting docker logs: {e}")
        return entries

    def parse_k8s_logs(
        self,
        pod: Optional[str] = None,
        namespace: Optional[str] = None,
        container: Optional[str] = None,
        lines: int = 100,
        context: Optional[str] = None,
    ) -> List[LogEntry]:
        """Get logs from a Kubernetes pod or smart-read a full namespace via kubectl."""
        from collectors.k8s_collector import K8sCollector
        collector = K8sCollector(namespace=namespace, context=context)
        entries = []

        if pod:
            raw_lines = collector.get_pod_logs(pod, container=container, lines=lines)
            source = f'k8s:{namespace or "default"}/{pod}'
            if container:
                source += f'/{container}'
            for line in raw_lines:
                entry = self.parse_line(line, source=source)
                if entry:
                    entries.append(entry)
            return entries

        namespace_logs = collector.get_namespace_logs(lines=lines, container=container)
        namespace_name = namespace or "default"
        for pod_name, raw_lines in namespace_logs.items():
            source = f'k8s:{namespace_name}/{pod_name}'
            if container:
                source += f'/{container}'
            for line in raw_lines:
                entry = self.parse_line(line, source=source)
                if entry:
                    entries.append(entry)
        return entries


class LogAnalyzer:
    """Analyze logs and detect issues"""
    
    def __init__(self):
        self.parser = LogParser()
        self.errors = []
        self.warnings = []
        self.stats = {'total': 0, 'errors': 0, 'warnings': 0, 'info': 0}
    
    def analyze(self, entries: List[LogEntry]) -> Dict:
        self.errors = []
        self.warnings = []
        self.stats = {'total': len(entries), 'error': 0, 'warning': 0, 'info': 0, 'debug': 0, 'critical': 0, 'fatal': 0}
        
        for entry in entries:
            level = entry.level.upper()
            level_key = level.lower()
            if level_key in self.stats:
                self.stats[level_key] = self.stats[level_key] + 1
            else:
                self.stats['info'] = self.stats.get('info', 0) + 1
            
            if level in ['ERROR', 'CRITICAL', 'FATAL']:
                self.errors.append(entry)
            elif level == 'WARNING':
                self.warnings.append(entry)
        
        return {
            'summary': self.stats,
            'errors': [e.to_dict() for e in self.errors[:50]],  # Limit to 50
            'warnings': [w.to_dict() for w in self.warnings[:50]],
            'analysis': self._generate_analysis()
        }
    
    def _generate_analysis(self) -> Dict:
        """Generate basic analysis without LLM"""
        analysis = {
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'error_patterns': self._find_patterns(self.errors),
            'warning_patterns': self._find_patterns(self.warnings),
            'recommendations': []
        }
        
        # Generate recommendations
        if len(self.errors) > 10:
            analysis['recommendations'].append('High error volume detected - investigate immediately')
        
        if len(self.warnings) > 20:
            analysis['recommendations'].append('Many warnings present - consider addressing root causes')
        
        # Check for common patterns
        error_msgs = ' '.join([e.message.lower() for e in self.errors])
        if 'memory' in error_msgs or 'oom' in error_msgs:
            analysis['recommendations'].append('Memory issues detected - check resource limits')
        if 'connection' in error_msgs or 'timeout' in error_msgs:
            analysis['recommendations'].append('Connection issues detected - check network/service availability')
        if 'permission' in error_msgs or 'denied' in error_msgs:
            analysis['recommendations'].append('Permission errors detected - review access controls')
        
        return analysis
    
    def _find_patterns(self, entries: List[LogEntry]) -> List[Dict]:
        """Find common error patterns"""
        patterns = {}
        for entry in entries:
            # Extract key parts of message
            msg = entry.message
            # Get first 50 chars as pattern key
            key = msg[:50] if len(msg) > 50 else msg
            patterns[key] = patterns.get(key, 0) + 1
        
        # Sort by count
        sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
        return [{'pattern': p[0], 'count': p[1]} for p in sorted_patterns[:10]]


class LLMAnalyzer:
    """Use LLM for advanced log analysis"""
    
    def __init__(self, provider: str = None, model: str = None, api_key: str = None):
        self.provider = provider or os.getenv('LLM_PROVIDER', 'openai')
        self.model = model or os.getenv('LLM_MODEL', 'gpt-4o-mini')
        self.api_key = api_key or self._get_provider_api_key()
        
        # Provider configs
        self.endpoints = {
            'openai': 'https://api.openai.com/v1/chat/completions',
            'anthropic': 'https://api.anthropic.com/v1/messages',
            'groq': 'https://api.groq.com/openai/v1/chat/completions',
            'minimax': 'https://api.minimax.io/v1/chat/completions',
        }

    def _get_provider_api_key(self) -> str:
        key_map = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'groq': 'GROQ_API_KEY',
            'minimax': 'MINIMAX_API_KEY',
        }
        return os.getenv(key_map.get(self.provider, 'OPENAI_API_KEY'), '')
    
    def analyze_with_llm(self, analysis: Dict) -> str:
        if not self.api_key:
            return "LLM not configured. Set OPENAI_API_KEY or other provider API key."
        
        # Build prompt
        summary = analysis.get('summary', {})
        errors = analysis.get('errors', [])[:10]
        
        prompt = f"""Analyze these log entries and provide insights:

Summary:
- Total: {summary.get('total', 0)}
- Errors: {summary.get('errors', 0)}
- Warnings: {summary.get('warnings', 0)}

Recent Errors:
{chr(10).join([f"- {e.get('message', '')[:100]}" for e in errors])}

Provide:
1. Root cause analysis
2. Recommended actions
3. Severity assessment

Be concise and actionable."""

        if self.provider == 'openai':
            return self._call_openai(prompt)
        elif self.provider == 'groq':
            return self._call_groq(prompt)
        elif self.provider == 'anthropic':
            return self._call_anthropic(prompt)
        elif self.provider == 'minimax':
            return self._call_minimax(prompt)
        else:
            return "Unsupported provider"
    
    def _call_openai(self, prompt: str) -> str:
        return self._call_chat_completions(prompt, 'openai')
    
    def _call_groq(self, prompt: str) -> str:
        return self._call_chat_completions(prompt, 'groq')  # Same API format

    def _call_minimax(self, prompt: str) -> str:
        return self._call_chat_completions(prompt, 'minimax')

    def _call_chat_completions(self, prompt: str, provider: str) -> str:
        try:
            import requests
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': self.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 500
            }
            resp = requests.post(
                self.endpoints[provider],
                headers=headers,
                json=payload,
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
            else:
                return f"API Error: {resp.status_code}"
        except Exception as e:
            return f"Error: {e}"
    
    def _call_anthropic(self, prompt: str) -> str:
        try:
            import requests
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01'
            }
            payload = {
                'model': self.model,
                'max_tokens': 500,
                'messages': [{'role': 'user', 'content': prompt}]
            }
            resp = requests.post(
                self.endpoints['anthropic'],
                headers=headers,
                json=payload,
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()['content'][0]['text']
            else:
                return f"API Error: {resp.status_code}"
        except Exception as e:
            return f"Error: {e}"


def main():
    parser = argparse.ArgumentParser(description='LogSentinel - AI-Powered Log Analyzer')
    parser.add_argument('files', nargs='*', help='Log files to analyze')
    parser.add_argument('-c', '--container', help='Docker container to analyze')
    parser.add_argument('-n', '--lines', type=int, default=100, help='Number of lines for docker/k8s logs')
    parser.add_argument('-o', '--output', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('--no-llm', action='store_true', help='Skip LLM analysis')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--pod', help='Kubernetes pod name to analyze')
    parser.add_argument('--namespace', help='Kubernetes namespace (reads all pods when --pod is not provided)')
    parser.add_argument('--k8s-container', dest='k8s_container', help='Container name within the Kubernetes pod')
    parser.add_argument('--context', help='Kubernetes context to use')

    args = parser.parse_args()

    # Collect logs
    entries = []
    parser_obj = LogParser()

    # From files
    for filepath in args.files:
        entries.extend(parser_obj.parse_file(filepath))

    # From docker
    if args.container:
        entries.extend(parser_obj.parse_docker_logs(args.container, args.lines))

    # From Kubernetes
    if args.pod or args.namespace:
        entries.extend(parser_obj.parse_k8s_logs(
            args.pod,
            namespace=args.namespace,
            container=args.k8s_container,
            lines=args.lines,
            context=args.context,
        ))
    
    if not entries:
        print("No log entries found")
        return
    
    # Analyze
    analyzer = LogAnalyzer()
    analysis = analyzer.analyze(entries)
    
    # LLM analysis
    if not args.no_llm:
        llm = LLMAnalyzer()
        llm_analysis = llm.analyze_with_llm(analysis)
        analysis['llm_insights'] = llm_analysis
    
    # Output
    if args.output == 'json':
        print(json.dumps(analysis, indent=2))
    else:
        # Human readable
        print("=== LogSentinel Analysis ===")
        print(f"\n📊 Summary:")
        s = analysis['summary']
        print(f"   Total: {s.get('total', 0)}")
        print(f"   Errors: {s.get('errors', 0)}")
        print(f"   Warnings: {s.get('warnings', 0)}")
        
        if analysis.get('errors'):
            print(f"\n🔴 Top Errors:")
            for e in analysis['errors'][:5]:
                print(f"   [{e['level']}] {e['message'][:80]}")
        
        if analysis.get('warnings'):
            print(f"\n🟡 Top Warnings:")
            for w in analysis['warnings'][:5]:
                print(f"   {w['message'][:80]}")
        
        a = analysis.get('analysis', {})
        if a.get('recommendations'):
            print(f"\n💡 Recommendations:")
            for rec in a['recommendations']:
                print(f"   - {rec}")
        
        if analysis.get('llm_insights'):
            print(f"\n🤖 LLM Insights:")
            print(analysis['llm_insights'])


if __name__ == '__main__':
    main()


# Additional collectors - imported automatically
def get_collector(collector_type: str, **kwargs):
    """Get a collector by type"""
    if collector_type == 'k8s':
        from collectors.k8s_collector import K8sCollector
        return K8sCollector(**kwargs)
    elif collector_type == 'syslog':
        from collectors.k8s_collector import SyslogCollector
        return SyslogCollector(**kwargs)
    elif collector_type == 'journald':
        from collectors.k8s_collector import JournaldCollector
        return JournaldCollector(**kwargs)
    return None


def generate_pdf(analysis: Dict, title: str = "Log Analysis") -> str:
    """Generate PDF from analysis"""
    from output.pdf_generator import PDFGenerator
    gen = PDFGenerator()
    return gen.generate(analysis, title)


def generate_html(analysis: Dict, title: str = "Log Analysis") -> str:
    """Generate HTML from analysis"""
    from output.pdf_generator import PDFGenerator
    gen = PDFGenerator()
    return gen.generate_html(analysis, title)


def check_and_alert(analysis: Dict):
    """Check alerts and send notifications"""
    from output.alerts import AlertManager
    manager = AlertManager()
    alerts = manager.check(analysis)
    if alerts:
        manager.send_alerts(alerts, analysis)
    return alerts


def main_cli():
    """CLI entry point"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog='logsentinel',
        description='LogSentinel - AI-Powered Log Analyzer'
    )
    parser.add_argument('files', nargs='*', help='Log files to analyze')
    parser.add_argument('-c', '--container', help='Docker container to analyze')
    parser.add_argument('-n', '--lines', type=int, default=100, help='Number of lines for docker/k8s logs')
    parser.add_argument('-o', '--output', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('--no-llm', action='store_true', help='Skip LLM analysis')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--version', action='version', version='LogSentinel 1.0.0')
    parser.add_argument('--pod', help='Kubernetes pod name to analyze')
    parser.add_argument('--namespace', help='Kubernetes namespace (reads all pods when --pod is not provided)')
    parser.add_argument('--k8s-container', dest='k8s_container', help='Container name within the Kubernetes pod')
    parser.add_argument('--context', help='Kubernetes context to use')

    args = parser.parse_args()

    # Collect logs
    entries = []
    parser_obj = LogParser()

    for filepath in args.files:
        entries.extend(parser_obj.parse_file(filepath))

    if args.container:
        entries.extend(parser_obj.parse_docker_logs(args.container, args.lines))

    # From Kubernetes
    if args.pod or args.namespace:
        entries.extend(parser_obj.parse_k8s_logs(
            args.pod,
            namespace=args.namespace,
            container=args.k8s_container,
            lines=args.lines,
            context=args.context,
        ))

    if not entries:
        print("No log entries found")
        return 1
    
    # Analyze
    analyzer = LogAnalyzer()
    analysis = analyzer.analyze(entries)
    
    # LLM analysis
    if not args.no_llm:
        llm = LLMAnalyzer()
        llm_analysis = llm.analyze_with_llm(analysis)
        analysis['llm_insights'] = llm_analysis
    
    # Output
    if args.output == 'json':
        import json
        print(json.dumps(analysis, indent=2))
    else:
        print("=== LogSentinel Analysis ===")
        s = analysis['summary']
        print(f"\n📊 Summary:")
        print(f"   Total: {s.get('total', 0)}")
        print(f"   Errors: {s.get('error', 0)}")
        print(f"   Warnings: {s.get('warning', 0)}")
        
        if analysis.get('errors'):
            print(f"\n🔴 Top Errors:")
            for e in analysis['errors'][:5]:
                print(f"   [{e['level']}] {e['message'][:80]}")
        
        if analysis.get('warnings'):
            print(f"\n🟡 Top Warnings:")
            for w in analysis['warnings'][:5]:
                print(f"   {w['message'][:80]}")
        
        a = analysis.get('analysis', {})
        if a.get('recommendations'):
            print(f"\n💡 Recommendations:")
            for rec in a['recommendations']:
                print(f"   - {rec}")
        
        if analysis.get('llm_insights'):
            print(f"\n🤖 LLM Insights:")
            print(analysis['llm_insights'])
    
    return 0


if __name__ == '__main__':
    sys.exit(main_cli())


class StreamingLogAnalyzer:
    """Streaming support for LLM responses"""
    
    def __init__(self, api_key: str, provider: str = "openai"):
        self.api_key = api_key
        self.provider = provider
    
    def analyze_stream(self, log_content: str, callback):
        """Analyze logs with streaming response"""
        # Split content into chunks
        chunks = [log_content[i:i+1000] for i in range(0, len(log_content), 1000)]
        
        for i, chunk in enumerate(chunks):
            # Process chunk
            result = self._analyze_chunk(chunk)
            callback(result)
        
        return "Analysis complete"
    
    def _analyze_chunk(self, chunk: str) -> str:
        """Analyze a single chunk"""
        # Simple analysis without real API call
        errors = chunk.lower().count('error')
        warnings = chunk.lower().count('warning')
        return f"Chunk analysis: {errors} errors, {warnings} warnings"


import time
from threading import Lock


class RateLimiter:
    """Rate limiting for API calls"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = []
        self.lock = Lock()
    
    def acquire(self) -> bool:
        """Acquire permission to make a request"""
        with self.lock:
            now = time.time()
            # Remove requests older than 1 minute
            self.requests = [r for r in self.requests if now - r < 60]
            
            if len(self.requests) < self.requests_per_minute:
                self.requests.append(now)
                return True
            return False
    
    def wait_if_needed(self):
        """Wait if rate limit exceeded"""
        while not self.acquire():
            time.sleep(1)


class SyslogServer:
    """Syslog server for receiving logs"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 514):
        self.host = host
        self.port = port
        self.running = False
        self.logs = []
    
    def start(self):
        """Start syslog server"""
        import socket
        self.running = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.port))
        
        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                message = data.decode('utf-8', errors='ignore')
                self.logs.append(message)
            except Exception as e:
                print(f"Error: {e}")
    
    def stop(self):
        """Stop syslog server"""
        self.running = False
    
    def get_logs(self) -> list:
        """Get collected logs"""
        return self.logs
