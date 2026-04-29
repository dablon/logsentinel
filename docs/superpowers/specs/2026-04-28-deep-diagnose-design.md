# LogSentinel Deep Namespace Diagnosis — Design Spec

**Date:** 2026-04-28
**Author:** Nicolas Alcaraz
**Status:** Draft

---

## 1. Overview

LogSentinel Deep Diagnosis (`--diagnose`) performs a comprehensive health assessment of a Kubernetes namespace. It goes beyond log analysis — collecting pod statuses, resource metrics, events, workload status, and service endpoints — then combines this with existing log parsing and optional LLM root cause analysis to produce a single actionable diagnostic report.

**Use case:** DevOps engineers triaging a degraded namespace, pre-deployment health checks, incident root cause investigation.

**Scope:**
- All pods in namespace with health classification (Running, CrashLoopBackOff, OOMKilled, ImagePullErr, Pending, etc.)
- Container restarts and status reasons
- Resource usage (CPU/memory via `kubectl top pods`) vs requests/limits
- Namespace events (warnings and normals) sorted by timestamp
- Workload status: Deployments, StatefulSets, DaemonSets (ready/desired)
- Services, HPA, PVC status
- Log analysis via existing `K8sCollector`
- Recommendation engine based on health findings
- LLM-powered root cause analysis (uses existing `LLMAnalyzer`)

**Out of scope:**
- Real-time streaming (use `--monitor` for that)
- Docker/syslog diagnosis
- Node-level diagnosis
- Network policy analysis
- Automated remediation

---

## 2. CLI

### New Flag

```bash
logsentinel --diagnose --namespace <ns> [--context <ctx>] [--lines <N>] [--no-llm] [--output text|json]
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--diagnose` | flag | — | Enable deep namespace diagnosis |
| `--namespace` | str | — | K8s namespace to diagnose (required with --diagnose) |
| `--context` | str | — | K8s context |
| `--lines` / `-n` | int | 100 | Log lines per pod budget |
| `--no-llm` | flag | — | Skip LLM root cause analysis |
| `--output` / `-o` | text/json | text | Output format |

### Output Format (text)

```
=== LogSentinel Namespace Diagnosis ===
Namespace: phoenix | Context: prod | Time: 2026-04-28 10:42:15

📦 PODS (5 found, 4 healthy, 1 unhealthy)
  [HEALTHY  ] api-deployment-7f8d5  Running, 0 restarts
  [UNHEALTHY] cache-9c4f2           CrashLoopBackOff, 12 restarts ⚠

⚡ RESOURCES
  api-deployment-7f8d5 ......... CPU: 120m/500m | MEM: 256Mi/512Mi

📋 EVENTS (3 warnings)
  [2026-04-28 10:40:00] WARNING  Back-off restarting failed container in cache-9c4f2

🔍 DEPLOYMENTS
  api-deployment ............... 3/3 ready
  cache-deployment ............. 0/1 ready ❌

📊 LOG ANALYSIS
  Total: 500 | Errors: 45 | Warnings: 32
  Top Errors:
    [ERROR] Database connection refused

💡 RECOMMENDATIONS
  - CrashLoopBackOff on cache-9c4f2: check pod logs
  - cache-deployment has 0/1 ready replicas

🤖 LLM ROOT CAUSE ANALYSIS
  [LLM analysis text...]
```

---

## 3. Architecture

### Components

```
NamespaceDiagnose (orchestrator)
  ├── K8sDiagnosticCollector (new) — kubectl calls for health data
  │     ├── get_pod_statuses()       → List[PodStatus]
  │     ├── get_resource_usage()     → List[ResourceUsage]
  │     ├── get_events()             → List[Event]
  │     ├── get_deployment_statuses()→ List[DeploymentStatus]
  │     ├── get_statefulset_statuses()→ List[StsStatus]
  │     ├── get_daemonset_statuses()  → List[DsStatus]
  │     ├── get_services()           → List[ServiceInfo]
  │     └── collect_all()            → DiagnosticSnapshot
  │
  ├── DiagnosticAnalyzer (new) — rule-based analysis
  │     ├── classify_pod_health()
  │     ├── detect_issues()          → List[DiagnosticIssue]
  │     └── generate_recommendations()
  │
  ├── LogParser (existing) — log collection + analysis
  ├── LogAnalyzer (existing) — pattern analysis
  ├── LLMAnalyzer (existing) — AI root cause analysis
  └── Formatter — text / json output
```

### Data Types

```python
@dataclass
class PodStatus:
    name: str
    namespace: str
    phase: str          # Running, Pending, Succeeded, Failed, Unknown
    ready: str          # "1/1", "0/1", etc.
    restarts: int
    age: str
    containers: List[ContainerStatus]
    conditions: List[str]  # PodScheduled, Ready, etc.
    node: str

@dataclass
class ContainerStatus:
    name: str
    ready: bool
    restart_count: int
    state: str          # running, waiting, terminated
    reason: str         # CrashLoopBackOff, OOMKilled, Completed, etc.
    image: str

@dataclass
class ResourceUsage:
    pod: str
    container: str
    cpu_usage: str      # "120m"
    cpu_request: str    # "500m"
    cpu_limit: str      # "1000m"
    mem_usage: str      # "256Mi"
    mem_request: str    # "512Mi"
    mem_limit: str      # "1Gi"

@dataclass
class Event:
    type: str           # Warning, Normal
    reason: str
    message: str
    timestamp: str
    source: str

@dataclass
class DeploymentStatus:
    name: str
    ready: str          # "3/3"
    desired: int
    available: int
    unavailable: int
    conditions: List[str]

@dataclass
class DiagnosticSnapshot:
    namespace: str
    context: str
    timestamp: str
    pods: List[PodStatus]
    resources: List[ResourceUsage]
    events: List[Event]
    deployments: List[DeploymentStatus]
    statefulsets: List[DeploymentStatus]
    daemonsets: List[DeploymentStatus]
    services: List[dict]
    hpas: List[dict]
    pvcs: List[dict]

@dataclass
class DiagnosticIssue:
    severity: str       # critical, warning, info
    source: str         # "pod/cache-9c4f2", "deployment/cache", etc.
    category: str       # crashloop, oom, imagepull, resource, scheduling, readiness
    message: str
```

---

## 4. Data Flow

```
User runs: logsentinel --diagnose --namespace phoenix

1. K8sDiagnosticCollector.collect_all(namespace, context)
   └─ Parallel kubectl calls:
        kubectl get pods -o json -n phoenix
        kubectl top pods -n phoenix
        kubectl get events -n phoenix --sort-by='.lastTimestamp'
        kubectl get deployments -o json -n phoenix
        kubectl get statefulsets -o json -n phoenix
        kubectl get daemonsets -o json -n phoenix
        kubectl get services -n phoenix
        kubectl get hpa -n phoenix
        kubectl get pvc -n phoenix
   └─ Parse JSON into DiagnosticSnapshot

2. K8sCollector.get_namespace_logs(namespace, lines)
   └─ Existing log collection (per pod, line budget split)

3. LogParser + LogAnalyzer (existing)
   └─ Parse log lines, detect patterns, build analysis dict

4. DiagnosticAnalyzer.analyze(snapshot, log_analysis)
   └─ Classify pod health (healthy / warning / critical)
   └─ Detect issues (CrashLoop, OOM, ImagePull, high restarts, etc.)
   └─ Generate recommendations

5. LLMAnalyzer.analyze_with_llm(combined_analysis) (unless --no-llm)
   └─ Forward structured diagnostic + log data to LLM
   └─ Get root cause analysis and remediation advice

6. Output formatter
   └─ Text: structured sections with emoji indicators
   └─ JSON: full diagnostic tree as JSON
```

---

## 5. Error Handling

| Scenario | Behavior |
|---|---|
| kubectl not installed | Show "kubectl not available" and exit (diagnosis requires it) |
| kubectl top fails (no metrics-server) | Show N/A for resource usage, note in recommendations |
| Empty namespace | Show "No pods found in namespace X" and exit |
| kubectl timeout on any call | Show partial results, note timeouts in output |
| Pod without logs | Show "no logs available" for that pod |
| HPA/PVC not found | Silently omit those sections |

---

## 6. Recommendation Rules

| Condition | Recommendation |
|---|---|
| CrashLoopBackOff | "Pod {name} is crash-looping. Check container logs for root cause." |
| OOMKilled | "Pod {name} was OOMKilled. Increase memory limits or fix memory leak." |
| ImagePullBackOff / ErrImagePull | "Pod {name} cannot pull image. Check image registry, credentials, or image name." |
| Pod Pending > 5min | "Pod {name} is stuck in Pending state. Check node resources or PVC binding." |
| High restarts (>10) | "Pod {name} has restarted {count} times. Investigate stability." |
| CPU usage > 80% limit | "Pod {name} CPU at {pct}% of limit. Consider increasing limit or scaling." |
| Memory usage > 80% limit | "Pod {name} memory at {pct}% of limit. Risk of OOM." |
| Deployment not fully ready | "Deployment {name} has {ready}/{desired} ready replicas." |
| Error logs > 10% total | "High error rate ({pct}%). See Top Errors section." |

---

## 7. Testing

```python
# tests/unit/test_diagnose.py

def test_k8s_diagnostic_collector_init():
    c = K8sDiagnosticCollector(namespace='test', context='kind-kind')
    assert c.namespace == 'test'

def test_empty_namespace_returns_empty_snapshot(monkeypatch):
    """Empty namespace returns snapshot with empty lists"""
    # ... mock kubectl to return no pods ...

def test_crashloop_detection():
    """CrashLoopBackOff is classified as CRITICAL with health 'unhealthy'"""
    # ...

def test_oomkilled_detection():
    """OOMKilled termination reason = CRITICAL"""
    # ...

def test_recommendation_for_high_restarts():
    """Pods with >10 restarts trigger a recommendation"""
    # ...
```

---

## 8. File Changes

| File | Change |
|---|---|
| `collectors/k8s_diagnose.py` | **New file** — K8sDiagnosticCollector, DiagnosticAnalyzer, data classes |
| `logsentinel.py` | Add `--diagnose` arg, `diagnose_namespace()` entry point, wire into `main()` and `main_cli()` |
| `tests/unit/test_diagnose.py` | **New file** — unit tests for collector and analyzer |
