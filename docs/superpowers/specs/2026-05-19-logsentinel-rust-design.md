# LogSentinel Rust — Design Specification

## 1. Overview

**Project:** LogSentinel in Rust — real-time K8s log analysis sentinel
**Type:** Monolithic Rust binary with embedded web dashboard
**Core:** CLI + Web share 100% of domain logic via `logsentinel-core` crate
**Goal:** Replace Python LogSentinel with production-quality Rust, TDD, clean architecture

## 2. Architecture

```
logsentinel/
├── logsentinel-core/        # Domain logic (no I/O at bottom, fully testable)
│   ├── src/
│   │   ├── lib.rs
│   │   ├── parser.rs        # LogParser, LogEntry, SeverityLevel
│   │   ├── analyzer.rs      # LogAnalyzer, pattern detection
│   │   ├── k8s/
│   │   │   ├── mod.rs
│   │   │   ├── collector.rs     # K8sCollector, LogStreamMerger
│   │   │   └── diagnostic.rs     # K8sDiagnosticCollector, DiagnosticAnalyzer
│   │   ├── llm.rs           # LLMAnalyzer (OpenAI, Anthropic, Groq, Minimax)
│   │   └── diagnose.rs      # DiagnosticIssue, DiagnosticSnapshot
├── logsentinel-cli/         # CLI binary
│   ├── src/
│   │   ├── main.rs          # clap entry, subcommands
│   │   ├── commands/
│   │   │   ├── mod.rs
│   │   │   ├── analyze.rs   # analyze command
│   │   │   ├── monitor.rs   # monitor command (ratatui)
│   │   │   └── diagnose_cmd.rs  # diagnose command
│   │   └── tui/
│   │       ├── mod.rs
│   │       └── display.rs   # TerminalDisplay, SeverityFilter, KeywordFilter
├── logsentinel-web/         # Web binary
│   ├── src/
│   │   ├── main.rs         # Rocket server
│   │   ├── routes/
│   │   │   ├── mod.rs
│   │   │   ├── dashboard.rs
│   │   │   ├── stream.rs    # SSE endpoint
│   │   │   └── api.rs       # JSON API endpoints
│   │   └── templates/
│   │       ├── mod.rs
│   │       ├── base.html
│   │       └── dashboard.html
├── logsentinel-compose/
│   ├── Dockerfile
│   └── docker-compose.yml
└── Cargo.toml              # Workspace manifest
```

## 3. Core Data Types

### LogEntry
```rust
pub struct LogEntry {
    pub timestamp: Option<DateTime<Utc>>,
    pub level: SeverityLevel,
    pub source: String,
    pub message: String,
}
```

### SeverityLevel
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum SeverityLevel {
    DEBUG = 0,
    INFO = 1,
    WARNING = 2,
    ERROR = 3,
    CRITICAL = 4,
}
```

### LogLine (for real-time streaming)
```rust
pub struct LogLine {
    pub timestamp: Option<DateTime<Utc>>,
    pub level: SeverityLevel,
    pub source: String,
    pub message: String,
    pub raw: String,
}
```

### DiagnosticSnapshot
```rust
pub struct DiagnosticSnapshot {
    pub namespace: String,
    pub context: Option<String>,
    pub timestamp: DateTime<Utc>,
    pub pods: Vec<PodHealth>,
    pub resources: Vec<ResourceUsage>,
    pub events: Vec<K8sEvent>,
    pub deployments: Vec<WorkloadStatus>,
    pub statefulsets: Vec<WorkloadStatus>,
    pub daemonsets: Vec<WorkloadStatus>,
    pub services: Vec<ServiceInfo>,
    pub hpas: Vec<HpaInfo>,
    pub pvcs: Vec<PvcInfo>,
    pub errors: Vec<String>,
}
```

## 4. CLI Commands

| Command | Description |
|---------|-------------|
| `logsentinel analyze <FILES...>` | Parse and analyze log files, output text or JSON |
| `logsentinel monitor -n <NAMESPACE>` | Real-time K8s log streaming via ratatui TUI |
| `logsentinel diagnose -n <NAMESPACE>` | Deep namespace diagnosis, text/JSON/HTML output |
| `logsentinel web --port <PORT>` | Start embedded web dashboard |
| `logsentinel -V` | Print version |

### Flags (shared)
- `--output, -o` — output format: `text` (default) or `json`
- `--level, -l` — minimum severity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `--context` — K8s context name
- `--no-llm` — skip LLM analysis

### Monitor flags
- `-n, --namespace` — K8s namespace (required, use `ALL` for all namespaces)
- `-f, --filter` — comma-separated keywords (AND logic)
- `-r, --refresh` — pod discovery refresh interval in seconds (default: 2)

### Diagnose flags
- `-n, --namespace` — K8s namespace (required)
- `--lines` — log lines per pod (default: 100)
- `--report` — generate HTML report
- `--report-dir` — report output directory (default: `./reports`)

### Web flags
- `--port` — web server port (default: 5050)

## 5. Web Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Redirect to `/dashboard` |
| `/dashboard` | GET | Main dashboard (Askama template) |
| `/stream` | GET | SSE real-time log stream |
| `/api/status` | GET | JSON: namespace, level, filters, running |
| `/api/pods` | GET | JSON: list of watched pods |
| `/api/diagnosis` | GET | JSON: latest namespace diagnosis |
| `/api/stop` | POST | Stop monitoring session |

## 6. SSE Event Format

```
event: log
data: {"timestamp":"2026-05-19T10:00:00Z","level":"ERROR","source":"kube-system/kube-proxy/","message":"Connection refused","raw":"..."}

event: stats
data: {"displayed":142,"errors":12,"warnings":31}
```

## 7. TDD Requirements

### logsentinel-core tests
- `parser.rs` — 30+ unit tests covering all log formats, edge cases
- `analyzer.rs` — tests with fixture data, verify error/warning counts, pattern detection
- `diagnostic.rs` — mock snapshots, assert issue detection
- `k8s/collector.rs` — mock kubectl output, verify parsing
- `llm.rs` — mock HTTP responses, verify prompt construction

### E2E tests
- Binary is invoked via `std::process::Command`
- Same test fixtures as Python version
- JSON output format matches Python version exactly

## 8. Docker

```dockerfile
# Multi-stage build
FROM rust:1.75 as builder
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY logsentinel-core/ logsentinel-core/
COPY logsentinel-cli/ logsentinel-cli/
COPY logsentinel-web/ logsentinel-web/
RUN cargo build --release --bin logsentinel-cli --bin logsentinel-web

FROM debian:bookworm-slim
COPY --from=builder /build/target/release/logsentinel-cli /usr/local/bin/
COPY --from=builder /build/target/release/logsentinel-web /usr/local/bin/
ENTRYPOINT ["logsentinel-web"]
```

```yaml
# docker-compose.yml
services:
  logsentinel:
    build: ../logsentinel-compose
    container_name: logsentinel
    environment:
      - KUBECONFIG=/.kube/config
    volumes:
      - ~/.kube:/.kube:ro
    ports:
      - "5050:5050"
    command: web --port 5050
    stdin_open: true
    tty: true
```

## 9. Dependencies (Cargo.toml)

```toml
[workspace]
members = ["logsentinel-core", "logsentinel-cli", "logsentinel-web"]

[workspace.dependencies]
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
chrono = { version = "0.4", features = ["serde"] }
thiserror = "1"
anyhow = "1"
reqwest = { version = "0.12", features = ["json"] }

[workspace.dependencies.logsentinel-core]
regex = "1"
once_cell = "1"

[workspace.dependencies.logsentinel-cli]
clap = { version = "4", features = ["derive"] }
ratatui = "0.26"
crossterm = "0.27"
tokio = { version = "1", features = ["full"] }

[workspace.dependencies.logsentinel-web]
rocket = { version = "0.5", features = ["json"] }
askama = "0.12"
tokio = { version = "1", features = ["full"] }
```

## 10. Error Handling

- All errors wrapped in `thiserror` enums per module
- `anyhow::Result<T>` for top-level command handlers
- K8s subprocess errors: log and continue, don't crash
- LLM API errors: return error string in output, don't fail analysis

## 11. Version

`logsentinel --version` outputs: `logsentinel 1.0.0`
