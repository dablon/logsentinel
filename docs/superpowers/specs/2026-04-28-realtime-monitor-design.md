# LogSentinel Real-Time Monitor — Design Spec

**Date:** 2026-04-28
**Author:** Nicolas Alcaraz
**Status:** Draft

---

## 1. Overview

LogSentinel Real-Time Monitor (`--monitor` / `-m`) continuously streams logs from Kubernetes pods, applying severity threshold and keyword filters, displaying them in a structured colored terminal output.

**Use case:** DevOps engineers monitoring a namespace for errors/warnings in real-time during deployments, incident response, or live debugging.

**Scope:**
- K8s namespace monitoring (all pods in namespace, unified stream)
- Severity filter + keyword filter
- Structured colored terminal output
- Auto-refresh display until interrupted (Ctrl+C)

**Out of scope:**
- LLM analysis (static analysis feature only)
- Docker container monitoring (future)
- Syslog/filetail monitoring (future)
- Alerting/notifications (future)

---

## 2. UI/CLI

### New CLI Flag

```bash
logsentinel --monitor --namespace <ns> [--level <severity>] [--filter "<kw1,kw2,...>"] [--lines <N>]
```

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--monitor` | `-m` | flag | — | Enable real-time monitoring mode |
| `--level` | `-l` | `DEBUG\|INFO\|WARNING\|ERROR\|CRITICAL` | `INFO` | Minimum severity to display |
| `--filter` | `-f` | `str` | — | Comma-separated keywords (AND logic) |
| `--refresh` | `-r` | `int` | `2` | Seconds between re-listing pods |

### Output Format

```
[2026-04-28 10:42:15] [ERROR  ] [api-7f8d5] Database connection refused at 10.0.0.5:5432
[2026-04-28 10:42:16] [WARNING] [worker-3] Slow query detected: 4,200 ms
[2026-04-28 10:42:17] [INFO   ] [proxy-1] Health check passed
```

**Color coding:**
- CRITICAL/ERROR: red
- WARNING: yellow
- INFO: cyan/blue
- DEBUG: gray

**Header on start:**
```
=== LogSentinel Monitor ===
Namespace: phoenix
Level: ERROR | Filter: connection,timeout
Press Ctrl+C to stop
---
```

---

## 3. Architecture

### Components

```
LogMonitor
  ├── K8sCollector (existing, list_pods + per-pod log streaming)
  ├── LogStreamMerger  — merges multiple pod streams into one
  ├── SeverityFilter   — filters by severity threshold
  ├── KeywordFilter   — filters by keyword list (AND)
  └── TerminalDisplay — colored, formatted output
```

### LogStreamMerger

Problem: `--follow` on a namespace isn't a single kubectl command — each pod needs its own `kubectl logs --follow`.

Solution: one background thread per discovered pod, each streaming log lines into a thread-safe priority queue sorted by timestamp. A single reader thread dequeues and dispatches to filters.

```python
class LogStreamMerger:
    def __init__(self, namespace, context, lines_back=50):
        self.pods = {}  # pod_name -> {'thread': Thread, 'queue': Queue}
        self.output_queue = Queue()  # merged output lines

    def start(self):
        # discover pods
        # for each pod: start background thread running kubectl logs --follow
        # each thread pushes raw lines to self.output_queue

    def stream(self) -> Generator[LogLine, None, None]:
        while True:
            yield self.output_queue.get()

    def stop(self):
        # signal all threads to stop, join them
```

### LogLine

```python
@dataclass
class LogLine:
    timestamp: Optional[datetime]
    level: str          # DEBUG, INFO, WARNING, ERROR, CRITICAL
    source: str         # "pod-name" or "pod-name/container"
    message: str
    raw: str            # original unparsed line
```

### SeverityFilter

```python
LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}

def passes(self, line: LogLine) -> bool:
    return LEVELS.get(line.level, 0) >= LEVELS[self.threshold]
```

### KeywordFilter

```python
def passes(self, line: LogLine) -> bool:
    if not self.keywords:
        return True
    return all(kw.lower() in line.message.lower() for kw in self.keywords)
```

### TerminalDisplay

- Uses ANSI color codes (cross-platform via `colorama` or `ANSI` lib)
- Clears screen on start, prepends lines (auto-scroll)
- Respects terminal width, truncates long lines
- Shows a brief stats line every N seconds: `Displayed: 142 | Errors: 12 | Warnings: 8`

### Integration Points

**Entry point** (`logsentinel.py`):
- Add `--monitor` arg parsing
- When `--monitor` active: call `monitor_namespace()` instead of one-shot analysis
- Pass `namespace`, `level`, `filter_keywords`, `context` to `LogMonitor`

**New file:** `collectors/k8s_monitor.py`

---

## 4. Data Flow

```
User runs: logsentinel --monitor --namespace phoenix --level ERROR --filter "timeout,refused"

LogMonitor.start()
  └─ K8sCollector.list_pods() → [pod1, pod2, pod3]
  └─ For each pod: spawn thread running:
       kubectl logs --follow pod -n phoenix
       Each line → merge into priority queue (sorted by timestamp)

Reader loop:
  while not stopped:
    line = output_queue.get()  # blocking
    if not SeverityFilter(line): continue
    if not KeywordFilter(line): continue
    TerminalDisplay.print(line)

Ctrl+C → LogMonitor.stop() → join all threads → exit
```

---

## 5. Error Handling

| Scenario | Behavior |
|---|---|
| Pod disappears mid-stream | Silently skip, log to stderr "Pod X gone, removing" |
| kubectl fails | Retry 3x with backoff, then show warning in display |
| Empty namespace | Show "No pods found" and exit |
| Queue gets backed up | Drop oldest lines if queue > 1000 (prevents memory bloat) |

---

## 6. Dependencies

New runtime dependency: `colorama` (for cross-platform ANSI colors on Windows).

```python
# requirements.txt (add)
colorama>=0.4.6
```

---

## 7. Testing

```python
# tests/unit/test_monitor.py

def test_severity_filter_error_above_warning():
    """ERROR and CRITICAL pass when level=ERROR"""
    sf = SeverityFilter(threshold='WARNING')
    assert not sf.passes(make_line('DEBUG'))
    assert not sf.passes(make_line('INFO'))
    assert sf.passes(make_line('WARNING'))
    assert sf.passes(make_line('ERROR'))
    assert sf.passes(make_line('CRITICAL'))

def test_keyword_filter_and_logic():
    """All keywords must be present"""
    kf = KeywordFilter(keywords=['timeout', 'db'])
    assert kf.passes(make_line('Connection timeout to db server'))
    assert not kf.passes(make_line('Connection timeout'))  # missing 'db'
    assert not kf.passes(make_line('Database error'))      # missing 'timeout'

def test_log_stream_merger_signals_stop():
    m = LogStreamMerger(namespace='test', context=None)
    m.start()
    m.stop()
    for pod_data in m.pods.values():
        pod_data['thread'].join(timeout=5)
        assert not pod_data['thread'].is_alive()
```

---

## 8. File Changes

| File | Change |
|---|---|
| `logsentinel.py` | Add `--monitor` args, wire in `monitor_namespace()` |
| `collectors/k8s_monitor.py` | **New file** — `LogMonitor`, `LogStreamMerger`, `SeverityFilter`, `KeywordFilter`, `TerminalDisplay` |
| `requirements.txt` | Add `colorama>=0.4.6` |
| `tests/unit/test_monitor.py` | **New file** — unit tests for filters and merger |

---

## 9. Out of Scope / Future

- Docker real-time monitoring
- LLM integration during monitoring
- Desktopnotifications / alerting
- Web UI / dashboard
- Syslog/file tail streaming
