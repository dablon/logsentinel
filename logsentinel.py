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


def monitor_namespace(namespace, context, level, filter_keywords, refresh):
    """Real-time monitor entry point"""
    from collectors.k8s_monitor import LogMonitor
    import signal
    import sys

    def signal_handler(sig, frame):
        print('\nStopping monitor...')
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    monitor = LogMonitor(
        namespace=namespace,
        context=context,
        level=level,
        filter_keywords=filter_keywords.split(',') if filter_keywords else [],
        refresh=refresh,
    )
    monitor.start()


def diagnose_namespace(namespace, context, lines, no_llm, output_format, report, report_dir):
    """Deep namespace diagnosis entry point"""
    from collectors.k8s_diagnose import K8sDiagnosticCollector, DiagnosticAnalyzer
    from collectors.k8s_collector import K8sCollector

    # 1. Collect diagnostic snapshot
    print(f"Collecting namespace health data for '{namespace}'...", file=sys.stderr)
    coll = K8sDiagnosticCollector(namespace=namespace, context=context)
    snapshot = coll.collect_all()

    # 2. Collect logs via existing pipeline
    k8s = K8sCollector(namespace=namespace, context=context)
    log_entries = []
    log_parser = LogParser()
    namespace_logs = k8s.get_namespace_logs(lines=lines)
    for pod_name, pod_log_lines in namespace_logs.items():
        for line in pod_log_lines:
            entry = log_parser.parse_line(line, source=f"k8s:{namespace}/{pod_name}")
            if entry:
                log_entries.append(entry)

    # 3. Run log analysis
    log_analysis = None
    if log_entries:
        analyzer = LogAnalyzer()
        log_analysis = analyzer.analyze(log_entries)

    # 4. Run diagnostic analysis
    diag_analyzer = DiagnosticAnalyzer()
    diagnosis = diag_analyzer.analyze(snapshot, log_analysis)

    # 5. LLM analysis (unless --no-llm)
    if not no_llm:
        llm = LLMAnalyzer()
        # Build a rich context for the LLM
        llm_prompt = _build_diagnostic_llm_prompt(diagnosis, log_analysis)
        llm_insights = llm.analyze_with_llm(llm_prompt)
        diagnosis['llm_insights'] = llm_insights

    # 6. Output
    if output_format == 'json':
        _output_diagnosis_json(diagnosis)
    else:
        _output_diagnosis_text(diagnosis)

    # 7. Generate report file if requested
    report_path = None
    if report:
        from output.diagnose_report import DiagnoseReportGenerator
        gen = DiagnoseReportGenerator(output_dir=report_dir)
        try:
            report_path = gen.generate_html(diagnosis)
            print(f"\n📄 Report saved: {report_path}")
        except Exception as e:
            print(f"\n⚠ Failed to generate report: {e}", file=sys.stderr)

    # Print collection errors if any
    if snapshot.errors:
        print(f"\n⚠️ Collection warnings:")
        for err in snapshot.errors:
            print(f"   - {err}")


def _build_diagnostic_llm_prompt(diagnosis: dict, log_analysis: dict) -> dict:
    """Build a structured prompt for LLM root cause analysis."""
    snapshot = diagnosis['snapshot']
    issues = diagnosis['issues']
    pod_summary = diagnosis['pod_summary']

    text_parts = []

    text_parts.append(f"NAMESPACE DIAGNOSIS: {snapshot.namespace}")
    text_parts.append(f"Timestamp: {snapshot.timestamp}")
    text_parts.append(f"Pods: {pod_summary['total']} total, {pod_summary['healthy']} healthy, "
                      f"{pod_summary['unhealthy']} unhealthy, {pod_summary['warning']} warning")

    if issues:
        text_parts.append("\nISSUES FOUND:")
        for i in issues:
            text_parts.append(f"  [{i.severity.upper()}] [{i.category}] {i.source}: {i.message}")

    if diagnosis.get('recommendations'):
        text_parts.append("\nRECOMMENDATIONS:")
        for r in diagnosis['recommendations']:
            text_parts.append(f"  - {r}")

    if log_analysis:
        ls = log_analysis.get('summary', {})
        text_parts.append(f"\nLOG ANALYSIS: {ls.get('total', 0)} entries, "
                          f"{ls.get('errors', 0)} errors, {ls.get('warnings', 0)} warnings")
        if log_analysis.get('errors'):
            text_parts.append("Top errors:")
            for e in log_analysis['errors'][:5]:
                text_parts.append(f"  [{e.get('level', 'ERROR')}] {e.get('message', '')}")

    return {
        'summary': {
            'total': pod_summary['total'],
            'errors': len([i for i in issues if i.severity == 'critical']),
            'warnings': len([i for i in issues if i.severity == 'warning']),
        },
        'errors': [{
            'level': i.severity.upper(),
            'message': i.message,
        } for i in issues],
        'analysis': {
            'error_patterns': [],
            'warnings': [i.message for i in issues if i.severity == 'warning'],
            'recommendations': diagnosis.get('recommendations', []),
        },
        '_llm_context': '\n'.join(text_parts),
    }


def _output_diagnosis_json(diagnosis: dict):
    """Output diagnosis as JSON."""
    snapshot = diagnosis['snapshot']
    output = {
        'namespace': snapshot.namespace,
        'context': snapshot.context,
        'timestamp': snapshot.timestamp,
        'pod_summary': diagnosis['pod_summary'],
        'pods': [
            {
                'name': p.name,
                'phase': p.phase,
                'ready': p.ready,
                'restarts': p.restarts,
                'age': p.age,
                'health': p.health,
                'node': p.node,
                'containers': [
                    {
                        'name': c.name,
                        'ready': c.ready,
                        'restart_count': c.restart_count,
                        'state': c.state,
                        'reason': c.reason,
                        'image': c.image,
                    } for c in p.containers
                ],
                'conditions': p.conditions,
            } for p in snapshot.pods
        ],
        'resources': [
            {
                'pod': r.pod,
                'cpu_usage': r.cpu_usage,
                'cpu_limit': r.cpu_limit,
                'mem_usage': r.mem_usage,
                'mem_limit': r.mem_limit,
            } for r in snapshot.resources
        ],
        'events': [
            {
                'type': e.type,
                'reason': e.reason,
                'message': e.message,
                'timestamp': e.timestamp,
            } for e in snapshot.events
        ],
        'workloads': {
            'deployments': [
                {'name': d.name, 'ready': d.ready, 'conditions': d.conditions}
                for d in snapshot.deployments
            ],
            'statefulsets': [
                {'name': s.name, 'ready': s.ready, 'conditions': s.conditions}
                for s in snapshot.statefulsets
            ],
            'daemonsets': [
                {'name': d.name, 'ready': d.ready, 'conditions': d.conditions}
                for d in snapshot.daemonsets
            ],
        },
        'services': snapshot.services,
        'hpas': snapshot.hpas,
        'pvcs': snapshot.pvcs,
        'issues': [
            {
                'severity': i.severity,
                'source': i.source,
                'category': i.category,
                'message': i.message,
            } for i in diagnosis.get('issues', [])
        ],
        'recommendations': diagnosis.get('recommendations', []),
        'llm_insights': diagnosis.get('llm_insights', ''),
        'collection_errors': snapshot.errors,
    }
    print(json.dumps(output, indent=2))


def _output_diagnosis_text(diagnosis: dict):
    """Output diagnosis as formatted text."""
    snapshot = diagnosis['snapshot']
    pod_summary = diagnosis['pod_summary']
    event_summary = diagnosis.get('event_summary', {})

    print("=== LogSentinel Namespace Diagnosis ===")
    print(f"Namespace: {snapshot.namespace} | Context: {snapshot.context or 'default'} | Time: {snapshot.timestamp[:19]}")

    # Pods
    print(f"\n📦 PODS ({pod_summary['total']} found, {pod_summary['healthy']} healthy, "
          f"{pod_summary['unhealthy']} unhealthy, {pod_summary['warning']} warning)")
    for pod in snapshot.pods:
        icon = { 'healthy': '✅', 'warning': '⚠️', 'critical': '❌', 'unknown': '❓' }.get(pod.health, '❓')
        health_tag = f"[{pod.health.upper():<9}]"
        print(f"  {icon} {health_tag} {pod.name:<40} {pod.phase}, {pod.restarts} restarts, age: {pod.age}")
        for c in pod.containers:
            if c.state != 'running' or c.reason:
                print(f"       └─ {c.name}: {c.state}, {c.reason}, image: {c.image}")

    # Resources
    if snapshot.resources:
        print(f"\n⚡ RESOURCES")
        for ru in snapshot.resources:
            cpu_str = f"CPU: {ru.cpu_usage}"
            if ru.cpu_limit and ru.cpu_limit not in ('N/A', '0'):
                cpu_str += f"/{ru.cpu_limit}"
            mem_str = f"MEM: {ru.mem_usage}"
            if ru.mem_limit and ru.mem_limit not in ('N/A', '0'):
                mem_str += f"/{ru.mem_limit}"
            print(f"  {ru.pod:<40} {cpu_str} | {mem_str}")
    else:
        print(f"\n⚡ RESOURCES: N/A (metrics-server not available)")

    # Events
    if snapshot.events:
        warning_events = [e for e in snapshot.events if e.type == 'Warning']
        normal_events = [e for e in snapshot.events if e.type == 'Normal']
        print(f"\n📋 EVENTS ({len(warning_events)} warnings, {len(normal_events)} normal)")
        displayed = warning_events if warning_events else snapshot.events[-10:]
        for e in displayed[-10:]:
            tag = '⚠️ ' if e.type == 'Warning' else '   '
            ts = e.timestamp[:19] if e.timestamp else 'N/A'
            print(f"  {tag}[{ts}] {e.message[:120]}")
    else:
        print(f"\n📋 EVENTS: None")

    # Deployments
    if snapshot.deployments:
        print(f"\n🔍 DEPLOYMENTS")
        for d in snapshot.deployments:
            icon = '✅' if d.available >= d.desired else '❌'
            print(f"  {icon} {d.name:<40} {d.ready} ready")
            for cond in d.conditions:
                if cond.startswith('!'):
                    print(f"       └─ {cond}")

    # StatefulSets
    if snapshot.statefulsets:
        print(f"\n🔍 STATEFULSETS")
        for s in snapshot.statefulsets:
            icon = '✅' if s.available >= s.desired else '❌'
            print(f"  {icon} {s.name:<40} {s.ready} ready")

    # DaemonSets
    if snapshot.daemonsets:
        print(f"\n🔍 DAEMONSETS")
        for d in snapshot.daemonsets:
            icon = '✅' if d.available >= d.desired else '❌'
            print(f"  {icon} {d.name:<40} {d.ready} ready")

    # Services
    if snapshot.services:
        print(f"\n🔗 SERVICES")
        for svc in snapshot.services:
            print(f"  {svc['name']:<40} {svc['type']:<10} {svc['cluster_ip']:<20} {svc['ports']}")

    # HPA
    if snapshot.hpas:
        print(f"\n📈 HPA")
        for hpa in snapshot.hpas:
            print(f"  {hpa['name']:<40} {hpa['reference']} {hpa['targets']} (min: {hpa['min_pods']}, max: {hpa['max_pods']}, replicas: {hpa['replicas']})")

    # PVC
    if snapshot.pvcs:
        print(f"\n💾 PVC")
        for pvc in snapshot.pvcs:
            print(f"  {pvc['name']:<40} {pvc['status']:<10} {pvc['volume']:<40} {pvc['capacity']}")

    # Issues
    if diagnosis.get('issues'):
        print(f"\n🚨 ISSUES FOUND ({len(diagnosis['issues'])})")
        for issue in diagnosis['issues']:
            icon_map = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}
            icon = icon_map.get(issue.severity, '⚪')
            print(f"  {icon} [{issue.severity.upper()}] [{issue.category}] {issue.source}")
            print(f"       {issue.message}")

    # Log analysis summary
    log_analysis = diagnosis.get('log_summary', {})
    if log_analysis:
        print(f"\n📊 LOG ANALYSIS")
        print(f"  Total: {log_analysis.get('total', 0)} | Errors: {log_analysis.get('errors', 0) or log_analysis.get('error', 0)} | Warnings: {log_analysis.get('warnings', 0) or log_analysis.get('warning', 0)}")

    # Recommendations
    if diagnosis.get('recommendations'):
        print(f"\n💡 RECOMMENDATIONS")
        for rec in diagnosis['recommendations']:
            print(f"  - {rec}")

    # LLM insights
    if diagnosis.get('llm_insights'):
        print(f"\n🤖 LLM ROOT CAUSE ANALYSIS")
        print(diagnosis['llm_insights'])


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
    parser.add_argument('--diagnose', action='store_true', help='Deep namespace diagnosis mode')
    parser.add_argument('-m', '--monitor', action='store_true', help='Enable real-time monitor mode')
    parser.add_argument('-l', '--level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Minimum severity level to display (default: INFO)')
    parser.add_argument('-f', '--filter', default='',
                        help='Comma-separated keywords (AND logic)')
    parser.add_argument('-r', '--refresh', type=int, default=2,
                        help='Pod discovery refresh interval in seconds (default: 2)')
    parser.add_argument('--report', action='store_true',
                        help='Generate an HTML report file from diagnosis')
    parser.add_argument('--report-dir', default='./reports',
                        help='Directory for report output (default: ./reports)')

    args = parser.parse_args()

    if args.monitor:
        if not args.namespace:
            parser.error('--monitor requires --namespace')
        monitor_namespace(
            namespace=args.namespace,
            context=args.context,
            level=args.level,
            filter_keywords=args.filter,
            refresh=args.refresh,
        )
        return

    if args.diagnose:
        if not args.namespace:
            parser.error('--diagnose requires --namespace')
        diagnose_namespace(
            namespace=args.namespace,
            context=args.context,
            lines=args.lines,
            no_llm=args.no_llm,
            output_format=args.output,
            report=args.report,
            report_dir=args.report_dir,
        )
        return

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
    parser.add_argument('--diagnose', action='store_true', help='Deep namespace diagnosis mode')
    parser.add_argument('-m', '--monitor', action='store_true', help='Enable real-time monitor mode')
    parser.add_argument('-l', '--level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Minimum severity level to display (default: INFO)')
    parser.add_argument('-f', '--filter', default='',
                        help='Comma-separated keywords (AND logic)')
    parser.add_argument('-r', '--refresh', type=int, default=2,
                        help='Pod discovery refresh interval in seconds (default: 2)')
    parser.add_argument('--report', action='store_true',
                        help='Generate an HTML report file from diagnosis')
    parser.add_argument('--report-dir', default='./reports',
                        help='Directory for report output (default: ./reports)')

    args = parser.parse_args()

    if args.monitor:
        if not args.namespace:
            parser.error('--monitor requires --namespace')
        monitor_namespace(
            namespace=args.namespace,
            context=args.context,
            level=args.level,
            filter_keywords=args.filter,
            refresh=args.refresh,
        )
        return 0

    if args.diagnose:
        if not args.namespace:
            parser.error('--diagnose requires --namespace')
        diagnose_namespace(
            namespace=args.namespace,
            context=args.context,
            lines=args.lines,
            no_llm=args.no_llm,
            output_format=args.output,
            report=args.report,
            report_dir=args.report_dir,
        )
        return 0

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
