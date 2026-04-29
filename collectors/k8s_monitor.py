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
    def __init__(self, namespace: str, context: str | None = None, lines_back: int = 50):
        self.namespace = namespace
        self.context = context
        self.lines_back = lines_back
        self.pods: dict[str, dict] = {}  # pod_name -> {'thread': Thread, 'process': Popen}
        self.output_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._pod_lock = threading.Lock()

    def _base_args(self) -> list[str]:
        args = ['kubectl']
        if self.context:
            args += ['--context', self.context]
        return args

    def _stream_pod(self, pod_name: str, container: str | None = None):
        cmd = self._base_args() + ['logs', '--follow', pod_name, '--tail', str(self.lines_back)]
        if self.namespace:
            cmd += ['-n', self.namespace]
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
            with self._pod_lock:
                if pod_name in self.pods:
                    self.pods[pod_name]['process'] = proc
            for line in iter(proc.stdout.readline, ''):
                if self._stop_event.is_set():
                    break
                if line:
                    self.output_queue.put((pod_name, line.rstrip('\n')))
            proc.stdout.close()
        except Exception as e:
            print(f'Error streaming pod {pod_name}: {e}', file=sys.stderr)

    def start(self):
        from collectors.k8s_collector import K8sCollector
        collector = K8sCollector(namespace=self.namespace, context=self.context)
        pod_names = collector.list_pods()
        for pod_name in pod_names:
            with self._pod_lock:
                self.pods[pod_name] = {'thread': None, 'process': None}
            t = threading.Thread(target=self._stream_pod, args=(pod_name,), daemon=True)
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
        namespace: str,
        context: str | None = None,
        level: str = 'INFO',
        filter_keywords: list[str] | None = None,
        refresh: int = 2,
    ):
        self.namespace = namespace
        self.context = context
        self.severity_filter = SeverityFilter(threshold=level)
        self.keyword_filter = KeywordFilter(keywords=filter_keywords)
        self.refresh = refresh
        self.merger = LogStreamMerger(namespace=namespace, context=context, lines_back=50)
        self.display = TerminalDisplay()
        self._stop_event = threading.Event()

    def _parse_raw_line(self, pod_name: str, raw: str) -> LogLine:
        """Best-effort parse of a raw log line into LogLine.
        Reuses existing LogParser from logsentinel.py for timestamp/level extraction."""
        from logsentinel import LogParser
        parser = LogParser()
        entry = parser.parse_line(raw, source=f'k8s:{self.namespace}/{pod_name}')
        if entry:
            return LogLine(
                timestamp=datetime.fromisoformat(entry.timestamp) if entry.timestamp else None,
                level=entry.level,
                source=pod_name,
                message=entry.message,
                raw=raw,
            )
        return LogLine(
            timestamp=None,
            level='INFO',
            source=pod_name,
            message=raw,
            raw=raw,
        )

    def start(self):
        self.display.print_header(self.namespace, self.severity_filter.threshold, self.keyword_filter.keywords)
        self.merger.start()
        stats_interval = 30
        last_stats = time.time()
        while not self._stop_event.is_set():
            for pod_name, raw_line in self.merger.stream():
                log_line = self._parse_raw_line(pod_name, raw_line)
                if not self.severity_filter.passes(log_line):
                    continue
                if not self.keyword_filter.passes(log_line):
                    continue
                self.display.print_line(log_line)
                now = time.time()
                if now - last_stats >= stats_interval:
                    self.display.print_stats()
                    last_stats = now

    def stop(self):
        self._stop_event.set()
        self.merger.stop()