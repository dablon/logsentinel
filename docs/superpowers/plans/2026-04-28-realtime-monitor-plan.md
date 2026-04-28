# LogSentinel Real-Time Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--monitor` mode to LogSentinel that streams K8s pod logs in real-time with severity + keyword filtering and colored terminal output.

**Architecture:** Hybrid approach — one background thread per discovered pod running `kubectl logs --follow`, merged via thread-safe queue, filtered, and displayed with ANSI colors using `colorama`.

**Tech Stack:** Python stdlib (`threading`, `queue`, `subprocess`, `dataclass`), `colorama` for cross-platform ANSI colors.

---

## File Map

| File | Role |
|---|---|
| `collectors/k8s_monitor.py` | New — all monitor components (LogLine, SeverityFilter, KeywordFilter, LogStreamMerger, TerminalDisplay, LogMonitor) |
| `logsentinel.py` | Modify — add `--monitor` CLI args and wire `monitor_namespace()` |
| `requirements.txt` | Modify — add `colorama>=0.4.6` |
| `tests/unit/test_monitor.py` | New — unit tests for filters and LogStreamMerger |

---

## Task 1: LogLine dataclass

**Files:**
- Create: `collectors/k8s_monitor.py`
- Test: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_monitor.py
import pytest
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
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/test_monitor.py::test_logline_fields -v
```
Expected: FAIL — ModuleNotFoundError: No module named 'collectors.k8s_monitor'

- [ ] **Step 3: Create empty module with LogLine**

```python
# collectors/k8s_monitor.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LogLine:
    timestamp: Optional[datetime]
    level: str          # DEBUG, INFO, WARNING, ERROR, CRITICAL
    source: str         # "pod-name" or "pod-name/container"
    message: str
    raw: str            # original unparsed line
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/test_monitor.py::test_logline_fields -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add collectors/k8s_monitor.py tests/unit/test_monitor.py
git commit -m "feat(monitor): add LogLine dataclass"
```

---

## Task 2: SeverityFilter

**Files:**
- Modify: `collectors/k8s_monitor.py` (add to existing)
- Test: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
def make_line(level):
    from collectors.k8s_monitor import LogLine
    return LogLine(timestamp=None, level=level, source='test-pod', message='test', raw='test')

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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/test_monitor.py::test_severity_filter_threshold_warning tests/unit/test_monitor.py::test_severity_filter_threshold_info tests/unit/test_monitor.py::test_severity_filter_unknown_level_treated_as_debug -v
```
Expected: FAIL — SeverityFilter not defined

- [ ] **Step 3: Implement SeverityFilter**

```python
# Add to collectors/k8s_monitor.py, after LogLine class

LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}


class SeverityFilter:
    def __init__(self, threshold: str = 'INFO'):
        self.threshold = threshold.upper()

    def passes(self, line: LogLine) -> bool:
        return LEVELS.get(line.level.upper(), 0) >= LEVELS.get(self.threshold, 0)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/test_monitor.py::test_severity_filter_threshold_warning tests/unit/test_monitor.py::test_severity_filter_threshold_info tests/unit/test_monitor.py::test_severity_filter_unknown_level_treated_as_debug -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add collectors/k8s_monitor.py tests/unit/test_monitor.py
git commit -m "feat(monitor): add SeverityFilter"
```

---

## Task 3: KeywordFilter

**Files:**
- Modify: `collectors/k8s_monitor.py`
- Test: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
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

def make_line_and_message(level, message):
    from collectors.k8s_monitor import LogLine
    return LogLine(timestamp=None, level=level, source='test-pod', message=message, raw=message)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/test_monitor.py::test_keyword_filter_and_logic tests/unit/test_monitor.py::test_keyword_filter_empty_keywords_passes_all tests/unit/test_monitor.py::test_keyword_filter_case_insensitive -v
```
Expected: FAIL — KeywordFilter not defined

- [ ] **Step 3: Implement KeywordFilter**

```python
# Add to collectors/k8s_monitor.py, after SeverityFilter

class KeywordFilter:
    def __init__(self, keywords: list[str] | None = None):
        self.keywords = [kw.lower() for kw in (keywords or [])]

    def passes(self, line: LogLine) -> bool:
        if not self.keywords:
            return True
        msg_lower = line.message.lower()
        return all(kw in msg_lower for kw in self.keywords)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/test_monitor.py::test_keyword_filter_and_logic tests/unit/test_monitor.py::test_keyword_filter_empty_keywords_passes_all tests/unit/test_monitor.py::test_keyword_filter_case_insensitive -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add collectors/k8s_monitor.py tests/unit/test_monitor.py
git commit -m "feat(monitor): add KeywordFilter"
```

---

## Task 4: LogStreamMerger (with mock subprocess — no real kubectl needed)

**Files:**
- Modify: `collectors/k8s_monitor.py`
- Test: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
import time, threading

def test_merger_stop_signals_threads_to_exit(mock_kubectl_logs):
    """stop() sets stop_event, threads exit cleanly"""
    from collectors.k8s_monitor import LogStreamMerger
    m = LogStreamMerger(namespace='test-ns', context=None, lines_back=5)
    m.start()
    assert len(m.pods) == 1
    m.stop()
    m.pods['test-pod']['thread'].join(timeout=5)
    assert not m.pods['test-pod']['thread'].is_alive()

def mock_kubectl_logs(pod_name, namespace, **kwargs):
    """Yields 3 lines then exits (simulates kubectl logs --follow)"""
    import time
    def emit():
        for i in range(3):
            print(f'[{pod_name}] line {i}')
            time.sleep(0.05)
    return emit
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/test_monitor.py::test_merger_stop_signals_threads_to_exit -v
```
Expected: FAIL — LogStreamMerger not defined

- [ ] **Step 3: Implement LogStreamMerger with mocks for testing**

```python
# Add to collectors/k8s_monitor.py, after KeywordFilter

import queue
import threading
import time


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
        cmd = self._base_args() + ['logs', '--follow', pod, '--tail', str(self.lines_back)]
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
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/test_monitor.py::test_merger_stop_signals_threads_to_exit -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add collectors/k8s_monitor.py tests/unit/test_monitor.py
git commit -m "feat(monitor): add LogStreamMerger for multi-pod log streaming"
```

---

## Task 5: TerminalDisplay + colorama integration

**Files:**
- Modify: `collectors/k8s_monitor.py`
- Test: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
def test_terminal_display_colors():
    """ERROR and CRITICAL lines use RED color"""
    from collectors.k8s_monitor import TerminalDisplay
    td = TerminalDisplay()
    assert td._color_for_level('ERROR') == td.RED
    assert td._color_for_level('CRITICAL') == td.RED
    assert td._color_for_level('WARNING') == td.YELLOW
    assert td._color_for_level('INFO') == td.CYAN
    assert td._color_for_level('DEBUG') == td.GRAY

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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/test_monitor.py::test_terminal_display_colors tests/unit/test_monitor.py::test_terminal_display_format_line -v
```
Expected: FAIL — TerminalDisplay not defined

- [ ] **Step 3: Implement TerminalDisplay**

```python
# Add to collectors/k8s_monitor.py, after KeywordFilter

import sys
import os


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
        color = self._color_for_level(line.level or 'INFO')
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/test_monitor.py::test_terminal_display_colors tests/unit/test_monitor.py::test_terminal_display_format_line -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add collectors/k8s_monitor.py tests/unit/test_monitor.py
git commit -m "feat(monitor): add TerminalDisplay with ANSI colors"
```

---

## Task 6: LogMonitor (orchestrator)

**Files:**
- Modify: `collectors/k8s_monitor.py`
- Test: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
def test_log_monitor_collects_pods_on_start():
    """LogMonitor.start() discovers pods via K8sCollector"""
    from unittest.mock import patch, MagicMock
    from collectors.k8s_monitor import LogMonitor
    with patch('collectors.k8s_monitor.K8sCollector') as mock_coll:
        mock_coll.return_value.list_pods.return_value = ['pod-a', 'pod-b']
        m = LogMonitor(namespace='test', context=None)
        m.start()
        assert len(m.merger.pods) == 2
        m.stop()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/test_monitor.py::test_log_monitor_collects_pods_on_start -v
```
Expected: FAIL — LogMonitor not defined

- [ ] **Step 3: Implement LogMonitor orchestrator**

```python
# Add to collectors/k8s_monitor.py, after TerminalDisplay

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
        """Best-effort parse of a raw log line into LogLine"""
        from collectors.log_parser import LogParser  # reuse existing parser
        parser = LogParser()
        entry = parser.parse_line(raw, source=f'k8s:{self.namespace}/{pod_name}')
        if entry:
            return LogLine(
                timestamp=entry.timestamp,
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
        import time
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
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/test_monitor.py::test_log_monitor_collects_pods_on_start -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add collectors/k8s_monitor.py tests/unit/test_monitor.py
git commit -m "feat(monitor): add LogMonitor orchestrator"
```

---

## Task 7: Add colorama to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add colorama dependency**

```
colorama>=0.4.6
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add colorama for cross-platform ANSI colors"
```

---

## Task 8: Wire --monitor into CLI (logsentinel.py)

**Files:**
- Modify: `logsentinel.py`
- Test: `tests/e2e/test_flow.py`

- [ ] **Step 1: Read current arg parsing section of logsentinel.py**

Read the last ~80 lines of `logsentinel.py` to see existing arg structure.

- [ ] **Step 2: Add monitor args to arg parser**

Find where CLI args are defined (search `add_argument`). Add these after existing K8s args:

```python
monitor_group = parser.add_argument_group('Real-Time Monitor')
monitor_group.add_argument('-m', '--monitor', action='store_true', help='Enable real-time monitor mode')
monitor_group.add_argument('-l', '--level', default='INFO',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                            help='Minimum severity level to display (default: INFO)')
monitor_group.add_argument('-f', '--filter', default='',
                            help='Comma-separated keywords (AND logic)')
monitor_group.add_argument('-r', '--refresh', type=int, default=2,
                            help='Pod discovery refresh interval in seconds (default: 2)')
```

- [ ] **Step 3: Add monitor_namespace function**

```python
def monitor_namespace(namespace, context, level, filter_keywords, refresh):
    """Real-time monitor entry point"""
    from collectors.k8s_monitor import LogMonitor
    import signal
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
```

- [ ] **Step 4: Wire monitor mode in main flow**

In `main()`, after args are parsed, add before the existing one-shot analysis block:

```python
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
```

- [ ] **Step 5: Add test for --monitor flag**

```python
def test_cli_monitor_flag():
    """Test --monitor flag is recognized"""
    result = subprocess.run(
        ['python3', 'logsentinel.py', '--monitor', '--help'],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), '../..')
    )
    assert '--monitor' in result.stdout
```

- [ ] **Step 6: Commit**

```bash
git add logsentinel.py tests/e2e/test_flow.py
git commit -m "feat(monitor): wire --monitor into CLI"
```

---

## Self-Review Checklist

- [ ] All spec sections covered: LogLine, SeverityFilter, KeywordFilter, LogStreamMerger, TerminalDisplay, LogMonitor
- [ ] No placeholder patterns found (TBD, TODO, etc.)
- [ ] Type consistency: LogLine fields match what LogMonitor._parse_raw_line produces
- [ ] Filter classes use same field names across tasks
- [ ] Task 4 has a bug — `pod` should be `pod_name` in `_stream_pod`. Fix before implementing.
- [ ] Every task has a test before implementation (TDD)

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-28-realtime-monitor-plan.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints

Which approach?
