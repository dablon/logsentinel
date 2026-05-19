"""Kubernetes monitor module for LogSentinel."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import queue
import threading
import time
import subprocess
import sys


@dataclass
class LogLine:
    timestamp: Optional[datetime]
    level: str          # DEBUG, INFO, WARNING, ERROR, CRITICAL
    source: str         # "pod-name" or "pod-name/container"
    message: str
    raw: str            # original unparsed line

    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'level': self.level,
            'source': self.source,
            'message': self.message,
            'raw': self.raw,
        }


LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}


class SeverityFilter:
    def __init__(self, threshold: str = 'INFO'):
        self.threshold = threshold.upper()

    def passes(self, line: LogLine) -> bool:
        return LEVELS.get(line.level.upper(), 0) >= LEVELS.get(self.threshold, 0)


class KeywordFilter:
    def __init__(self, keywords: list[str] | None = None):
        self.keywords = [kw.lower() for kw in (keywords or [])]

    def passes(self, line: LogLine) -> bool:
        if not self.keywords:
            return True
        msg_lower = line.message.lower()
        return all(kw in msg_lower for kw in self.keywords)


class TerminalDisplay:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    CLEAR = '\033[2J\033[H'

    def __init__(self):
        self.displayed = 0
        self.error_count = 0
        self.warning_count = 0
        self._last_stats_print = 0

    def _color_for_level(self, level: str) -> str:
        level = level.upper()
        if level in ('ERROR', 'CRITICAL'):
            return self.RED
        if level == 'WARNING':
            return self.YELLOW
        if level == 'INFO':
            return self.CYAN
        return self.GRAY

    def _level_str(self, level: str) -> str:
        return f'{level.upper():<7}'

    def _format_line(self, line: LogLine) -> str:
        ts = line.timestamp.strftime('%Y-%m-%d %H:%M:%S') if line.timestamp else 'N/A'
        lvl = self._level_str(line.level or 'INFO')
        source = f'[{line.source}]'
        msg = line.message
        return f'[{ts}] [{lvl}] {source} {msg}'

    def print_line(self, line: LogLine):
        color = self._color_for_level(line.level or 'INFO')
        formatted = self._format_line(line)
        print(f'{color}{formatted}{self.RESET}', flush=True)
        self.displayed += 1
        if (line.level or '').upper() in ('ERROR', 'CRITICAL'):
            self.error_count += 1
        elif (line.level or '').upper() == 'WARNING':
            self.warning_count += 1

    def print_header(self, namespace: str, level: str, filter_keywords: list[str]):
        print(self.CLEAR, end='')
        print(f'=== LogSentinel Monitor ===')
        print(f'Namespace: {namespace}')
        level_str = level.upper() if level else 'INFO'
        kw_str = ', '.join(filter_keywords) if filter_keywords else 'none'
        print(f'Level: {level_str} | Filter: {kw_str}')
        print('Press Ctrl+C to stop')
        print('---', flush=True)

    def print_stats(self):
        print(f'Displayed: {self.displayed} | Errors: {self.error_count} | Warnings: {self.warning_count}', flush=True)


class LogStreamMerger:
    def __init__(self, namespace: str | None, context: str | None = None, lines_back: int = 50):
        self.namespace = namespace
        self.context = context
        self.lines_back = lines_back
        # pod_key -> {'thread': Thread, 'process': Popen, 'namespace': str}
        # key is (namespace, pod_name) when namespace is None (all namespaces),
        # otherwise just pod_name for backwards compatibility
        self.pods: dict[str, dict] = {}
        self.output_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._pod_lock = threading.Lock()

    def _base_args(self) -> list[str]:
        args = ['kubectl']
        if self.context:
            args += ['--context', self.context]
        return args

    def _stream_pod(self, pod_name: str, namespace: str | None, container: str | None = None):
        cmd = self._base_args() + ['logs', '--follow', pod_name, '--tail', str(self.lines_back)]
        if namespace:
            cmd += ['-n', namespace]
        if container:
            cmd += ['-c', container]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
            )
            # In all-namespaces mode (self.namespace is None), use full key with namespace
            # In single namespace mode, use just pod_name
            if self.namespace is None and namespace:
                pod_key = f'{namespace}/{pod_name}'
            else:
                pod_key = pod_name
            with self._pod_lock:
                if pod_key in self.pods:
                    self.pods[pod_key]['process'] = proc
            for line in iter(proc.stdout.readline, ''):
                if self._stop_event.is_set():
                    break
                if line:
                    self.output_queue.put((namespace, pod_name, line.rstrip('\n')))
            proc.stdout.close()
        except Exception as e:
            print(f'Error streaming pod {pod_name}: {e}', file=sys.stderr)

    def _get_pods_with_namespace(self) -> list[tuple[str, str]]:
        """Return list of (namespace, pod_name) tuples. Only for all-namespaces mode."""
        cmd = self._base_args() + ['get', 'pods', '--all-namespaces', '-o', 'json']
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
            )
            if result.returncode != 0:
                return []
            import json
            data = json.loads(result.stdout)
            pairs = []
            for item in data.get('items', []):
                ns = item.get('metadata', {}).get('namespace', '')
                name = item.get('metadata', {}).get('name', '')
                if ns and name:
                    pairs.append((ns, name))
            return pairs
        except Exception as e:
            print(f'Error listing pods with namespaces: {e}', file=sys.stderr)
            return []

    def start(self):
        from collectors.k8s_collector import K8sCollector
        collector = K8sCollector(namespace=self.namespace, context=self.context)
        pod_names = collector.list_pods()
        if self.namespace is None:
            # All namespaces mode: get pods with their namespaces
            pod_list = self._get_pods_with_namespace()
            for namespace, pod_name in pod_list:
                pod_key = f'{namespace}/{pod_name}'
                with self._pod_lock:
                    self.pods[pod_key] = {'thread': None, 'process': None, 'namespace': namespace}
                t = threading.Thread(target=self._stream_pod, args=(pod_name, namespace), daemon=True)
                self.pods[pod_key]['thread'] = t
                t.start()
        else:
            for pod_name in pod_names:
                with self._pod_lock:
                    self.pods[pod_name] = {'thread': None, 'process': None, 'namespace': self.namespace}
                t = threading.Thread(target=self._stream_pod, args=(pod_name, self.namespace), daemon=True)
                self.pods[pod_name]['thread'] = t
                t.start()

    def stream(self):
        while not self._stop_event.is_set():
            try:
                item = self.output_queue.get(timeout=0.5)
                yield item
            except queue.Empty:
                continue

    def stop(self):
        self._stop_event.set()
        with self._pod_lock:
            for pod_name, pod_data in list(self.pods.items()):
                proc = pod_data.get('process')
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                thread = pod_data.get('thread')
                if thread:
                    thread.join(timeout=3)


class LogMonitor:
    def __init__(
        self,
        namespace: str | None,
        context: str | None = None,
        level: str = 'INFO',
        filter_keywords: list[str] | None = None,
        refresh: int = 2,
        web_queue: queue.Queue | None = None,
    ):
        self.namespace = namespace
        self.context = context
        self.severity_filter = SeverityFilter(threshold=level)
        self.keyword_filter = KeywordFilter(keywords=filter_keywords)
        self.refresh = refresh
        self.merger = LogStreamMerger(namespace=namespace, context=context, lines_back=50)
        self.display = TerminalDisplay()
        self._stop_event = threading.Event()
        self.web_queue = web_queue
        self._cluster_state = {'context': context}
        self._cluster_lock = threading.Lock()

    def switch_cluster(self, new_context: str | None):
        """Switch to a new cluster context and restart the merger."""
        with self._cluster_lock:
            old_context = self._cluster_state.get('context')
            if old_context == new_context:
                return
            self._cluster_state['context'] = new_context
        # Signal the merger to stop so the stream loop picks up the change
        self.merger.stop()

    def get_cluster_context(self) -> str | None:
        with self._cluster_lock:
            return self._cluster_state.get('context')

    def _parse_raw_line(self, namespace: str | None, pod_name: str, raw: str) -> LogLine:
        """Best-effort parse of a raw log line into LogLine.
        Reuses existing LogParser from logsentinel.py for timestamp/level extraction."""
        from logsentinel import LogParser
        parser = LogParser()
        ns_display = namespace if namespace is not None else 'all-namespaces'
        entry = parser.parse_line(raw, source=f'k8s:{ns_display}/{pod_name}')
        if entry:
            return LogLine(
                timestamp=datetime.fromisoformat(entry.timestamp) if entry.timestamp else None,
                level=entry.level,
                source=f'{namespace}/{pod_name}' if namespace else pod_name,
                message=entry.message,
                raw=raw,
            )
        return LogLine(
            timestamp=None,
            level='INFO',
            source=f'{namespace}/{pod_name}' if namespace else pod_name,
            message=raw,
            raw=raw,
        )

    def start(self):
        self.display.print_header(self.namespace or 'all-namespaces', self.severity_filter.threshold, self.keyword_filter.keywords)
        self.merger.start()
        stats_interval = 30
        last_stats = time.time()
        while not self._stop_event.is_set():
            for namespace, pod_name, raw_line in self.merger.stream():
                log_line = self._parse_raw_line(namespace, pod_name, raw_line)
                if not self.severity_filter.passes(log_line):
                    continue
                if not self.keyword_filter.passes(log_line):
                    continue
                self.display.print_line(log_line)
                if self.web_queue is not None:
                    try:
                        self.web_queue.put_nowait(log_line)
                    except queue.Full:
                        pass
                now = time.time()
                if now - last_stats >= stats_interval:
                    self.display.print_stats()
                    last_stats = now

    def stop(self):
        self._stop_event.set()
        self.merger.stop()