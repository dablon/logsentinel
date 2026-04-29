"""
Deep namespace diagnostic collector and analyzer for Kubernetes.

Collects pod statuses, resource usage, events, workload status, services,
and combines with log analysis for a comprehensive namespace health report.
"""
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class ContainerStatus:
    name: str
    ready: bool
    restart_count: int
    state: str          # running, waiting, terminated
    reason: str         # CrashLoopBackOff, OOMKilled, Completed, Started, etc.
    image: str


@dataclass
class PodHealth:
    name: str
    namespace: str
    phase: str          # Running, Pending, Succeeded, Failed, Unknown
    ready: str          # "1/1", "0/1", "0/2", etc.
    restarts: int
    age: str
    containers: List[ContainerStatus] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    node: str = ""
    health: str = "unknown"  # healthy, warning, critical


@dataclass
class ResourceUsage:
    pod: str
    cpu_usage: str      # "120m" or "N/A"
    cpu_limit: str      # "500m" or "N/A" or "0"
    mem_usage: str      # "256Mi" or "N/A"
    mem_limit: str      # "512Mi" or "N/A" or "0"


@dataclass
class K8sEvent:
    type: str           # Warning, Normal
    reason: str
    message: str
    timestamp: str
    source_component: str
    source_host: str


@dataclass
class WorkloadStatus:
    name: str
    kind: str           # Deployment, StatefulSet, DaemonSet
    ready: str          # "3/3"
    desired: int
    available: int
    unavailable: int
    conditions: List[str] = field(default_factory=list)


@dataclass
class DiagnosticSnapshot:
    namespace: str
    context: str
    timestamp: str
    pods: List[PodHealth] = field(default_factory=list)
    resources: List[ResourceUsage] = field(default_factory=list)
    events: List[K8sEvent] = field(default_factory=list)
    deployments: List[WorkloadStatus] = field(default_factory=list)
    statefulsets: List[WorkloadStatus] = field(default_factory=list)
    daemonsets: List[WorkloadStatus] = field(default_factory=list)
    services: List[Dict[str, str]] = field(default_factory=list)
    hpas: List[Dict[str, str]] = field(default_factory=list)
    pvcs: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)  # collection errors


@dataclass
class DiagnosticIssue:
    severity: str       # critical, warning, info
    source: str         # "pod/cache-9c4f2", "deployment/cache", etc.
    category: str       # crashloop, oom, imagepull, resource, scheduling, readiness, events, restarts
    message: str


# ── Collector ───────────────────────────────────────────────────────────────

class K8sDiagnosticCollector:
    """Collect comprehensive namespace health data via kubectl."""

    def __init__(self, namespace: str, context: Optional[str] = None):
        self.namespace = namespace
        self.context = context

    def _base_args(self) -> List[str]:
        args = ['kubectl']
        if self.context:
            args += ['--context', self.context]
        return args

    def _run_json(self, args: List[str], timeout: int = 30) -> Optional[Any]:
        """Run kubectl and parse JSON output. Returns None on failure."""
        cmd = self._base_args() + args + ['-n', self.namespace]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
            return None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, Exception):
            return None

    def _run_text(self, args: List[str], timeout: int = 30) -> Optional[str]:
        """Run kubectl and return raw text output. Returns None on failure."""
        cmd = self._base_args() + args + ['-n', self.namespace]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=timeout
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None

    # ── Pod Status ──────────────────────────────────────────────────────

    def get_pod_statuses(self) -> List[PodHealth]:
        data = self._run_json(['get', 'pods', '-o', 'json'])
        if not data:
            return []

        pods = []
        for item in data.get('items', []):
            metadata = item.get('metadata', {})
            spec = item.get('spec', {})
            status = item.get('status', {})

            name = metadata.get('name', 'unknown')
            phase = status.get('phase', 'Unknown')
            node = spec.get('nodeName', '')
            start_time = status.get('startTime', '')

            # Calculate age
            age = self._calculate_age(start_time)

            # Container statuses
            containers = []
            total_containers = 0
            ready_containers = 0
            total_restarts = 0

            for cs in status.get('containerStatuses', []):
                c_ready = cs.get('ready', False)
                c_restarts = cs.get('restartCount', 0)
                c_state = 'unknown'
                c_reason = ''
                c_image = cs.get('image', '')

                state_dict = cs.get('state', {})
                if 'running' in state_dict:
                    c_state = 'running'
                    c_reason = 'Started'
                elif 'waiting' in state_dict:
                    c_state = 'waiting'
                    c_reason = state_dict['waiting'].get('reason', '')
                elif 'terminated' in state_dict:
                    c_state = 'terminated'
                    c_reason = state_dict['terminated'].get('reason', '')

                total_containers += 1
                if c_ready:
                    ready_containers += 1
                total_restarts += c_restarts

                containers.append(ContainerStatus(
                    name=cs.get('name', ''),
                    ready=c_ready,
                    restart_count=c_restarts,
                    state=c_state,
                    reason=c_reason,
                    image=c_image,
                ))

            # Pod conditions
            conditions = []
            for cond in status.get('conditions', []):
                if cond.get('status') == 'True':
                    ctype = cond.get('type', '')
                    reason = cond.get('reason', '')
                    conditions.append(f"{ctype}:{reason}" if reason else ctype)
                elif cond.get('status') == 'False':
                    ctype = cond.get('type', '')
                    reason = cond.get('reason', '')
                    msg = cond.get('message', '')
                    conditions.append(f"!{ctype}:{reason}" if reason else f"!{ctype}")

            pod = PodHealth(
                name=name,
                namespace=self.namespace,
                phase=phase,
                ready=f"{ready_containers}/{total_containers}",
                restarts=total_restarts,
                age=age,
                containers=containers,
                conditions=conditions,
                node=node,
                health=self._classify_pod_health(containers, phase, total_restarts),
            )
            pods.append(pod)

        return pods

    # ── Resource Usage (kubectl top) ────────────────────────────────────

    def get_resource_usage(self) -> List[ResourceUsage]:
        """Get CPU/memory usage via kubectl top. Returns empty list if metrics-server unavailable."""
        raw = self._run_text(['top', 'pods', '--no-headers'])
        if not raw:
            return []

        resources = []
        for line in raw.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 3:
                continue

            name = parts[0]
            cpu_raw = parts[1] if len(parts) > 1 else 'N/A'
            mem_raw = parts[2] if len(parts) > 2 else 'N/A'

            resources.append(ResourceUsage(
                pod=name,
                cpu_usage=cpu_raw,
                cpu_limit='N/A',
                mem_usage=mem_raw,
                mem_limit='N/A',
            ))
        return resources

    def get_resource_limits(self) -> Dict[str, Dict[str, str]]:
        """Extract resource requests/limits from pod specs."""
        data = self._run_json(['get', 'pods', '-o', 'json'])
        if not data:
            return {}

        limits = {}
        for item in data.get('items', []):
            pod_name = item.get('metadata', {}).get('name', '')
            pod_containers = {}
            for container in item.get('spec', {}).get('containers', []):
                c_resources = container.get('resources', {})
                c_requests = c_resources.get('requests', {})
                c_limits = c_resources.get('limits', {})
                pod_containers[container['name']] = {
                    'cpu_request': c_requests.get('cpu', '0'),
                    'cpu_limit': c_limits.get('cpu', '0'),
                    'mem_request': c_requests.get('memory', '0'),
                    'mem_limit': c_limits.get('memory', '0'),
                }
            limits[pod_name] = pod_containers
        return limits

    # ── Events ──────────────────────────────────────────────────────────

    def get_events(self, limit: int = 100) -> List[K8sEvent]:
        data = self._run_json([
            'get', 'events',
            '--sort-by=.lastTimestamp',
            '-o', 'json',
        ])
        if not data:
            return []

        events = []
        for item in data.get('items', []):
            ev_type = item.get('type', 'Normal')
            reason = item.get('reason', '')
            message = item.get('message', '')
            timestamp = item.get('lastTimestamp') or item.get('eventTime') or item.get('metadata', {}).get('creationTimestamp', '')
            source = item.get('source', {})
            source_component = source.get('component', '')
            source_host = source.get('host', '')

            events.append(K8sEvent(
                type=ev_type,
                reason=reason,
                message=message,
                timestamp=timestamp,
                source_component=source_component,
                source_host=source_host,
            ))
        return events[-limit:]

    # ── Workloads ───────────────────────────────────────────────────────

    def get_workloads(self, kind: str) -> List[WorkloadStatus]:
        kind_lower = kind.lower()
        data = self._run_json(['get', kind_lower, '-o', 'json'])
        if not data:
            return []

        workloads = []
        for item in data.get('items', []):
            name = item.get('metadata', {}).get('name', '')
            status = item.get('status', {})

            # replicas/ready/available differ slightly between kinds
            desired = status.get('replicas', 0) or status.get('desiredNumberScheduled', 0)
            ready_count = status.get('readyReplicas', 0) or status.get('numberReady', 0)
            available = status.get('availableReplicas', ready_count) or status.get('numberAvailable', ready_count)
            unavailable = status.get('unavailableReplicas', 0) or status.get('numberUnavailable', 0)

            conditions = []
            for cond in status.get('conditions', []):
                ctype = cond.get('type', '')
                cstatus = cond.get('status', '')
                reason = cond.get('reason', '')
                if cstatus == 'True':
                    conditions.append(f"{ctype}:{reason}" if reason else ctype)
                elif cstatus == 'False':
                    conditions.append(f"!{ctype}:{reason}" if reason else f"!{ctype}")

            workloads.append(WorkloadStatus(
                name=name,
                kind=kind,
                ready=f"{ready_count}/{desired}" if desired > 0 else "0/0",
                desired=desired,
                available=available,
                unavailable=unavailable,
                conditions=conditions,
            ))
        return workloads

    # ── Services ────────────────────────────────────────────────────────

    def get_services(self) -> List[Dict[str, str]]:
        data = self._run_json(['get', 'svc', '-o', 'json'])
        if not data:
            return []

        services = []
        for item in data.get('items', []):
            name = item.get('metadata', {}).get('name', '')
            spec = item.get('spec', {})
            svc_type = spec.get('type', 'ClusterIP')
            cluster_ip = spec.get('clusterIP', '')
            ports = spec.get('ports', [])
            port_strs = []
            for p in ports:
                port = p.get('port', '')
                target_port = p.get('targetPort', '')
                protocol = p.get('protocol', 'TCP')
                if target_port:
                    port_strs.append(f"{port}:{target_port}/{protocol}")
                else:
                    port_strs.append(f"{port}/{protocol}")

            services.append({
                'name': name,
                'type': svc_type,
                'cluster_ip': cluster_ip,
                'ports': ', '.join(port_strs) if port_strs else 'none',
            })
        return services

    # ── HPA ─────────────────────────────────────────────────────────────

    def get_hpas(self) -> List[Dict[str, str]]:
        raw = self._run_text(['get', 'hpa', '--no-headers'])
        if not raw:
            return []

        hpas = []
        for line in raw.strip().split('\n'):
            parts = line.split()
            if len(parts) < 5:
                continue
            hpas.append({
                'name': parts[0],
                'reference': parts[1] if len(parts) > 1 else '',
                'targets': parts[2] if len(parts) > 2 else '',
                'min_pods': parts[3] if len(parts) > 3 else '',
                'max_pods': parts[4] if len(parts) > 4 else '',
                'replicas': parts[5] if len(parts) > 5 else '',
            })
        return hpas

    # ── PVC ─────────────────────────────────────────────────────────────

    def get_pvcs(self) -> List[Dict[str, str]]:
        raw = self._run_text(['get', 'pvc', '--no-headers'])
        if not raw:
            return []

        pvcs = []
        for line in raw.strip().split('\n'):
            parts = line.split()
            if len(parts) < 3:
                continue
            pvcs.append({
                'name': parts[0],
                'status': parts[1] if len(parts) > 1 else '',
                'volume': parts[2] if len(parts) > 2 else '',
                'capacity': parts[3] if len(parts) > 3 else '',
                'access_modes': parts[4] if len(parts) > 4 else '',
            })
        return pvcs

    # ── Collect All ─────────────────────────────────────────────────────

    def collect_all(self) -> DiagnosticSnapshot:
        """Gather all diagnostic data for the namespace."""
        errors = []

        try:
            pods = self.get_pod_statuses()
        except Exception as e:
            pods = []
            errors.append(f"Pod status collection failed: {e}")

        try:
            resource_usage = self.get_resource_usage()
        except Exception as e:
            resource_usage = []
            errors.append(f"Resource usage collection failed: {e}")

        # Enrich resource usage with limits from pod specs
        if resource_usage:
            limits = self.get_resource_limits()
            for ru in resource_usage:
                pod_limits = limits.get(ru.pod, {})
                # Take first container's limits as representative
                if pod_limits:
                    first = next(iter(pod_limits.values()), {})
                    ru.cpu_limit = first.get('cpu_limit', 'N/A') or 'N/A'
                    ru.mem_limit = first.get('mem_limit', 'N/A') or 'N/A'

        try:
            events = self.get_events()
        except Exception as e:
            events = []
            errors.append(f"Event collection failed: {e}")

        try:
            deployments = self.get_workloads('Deployment')
        except Exception as e:
            deployments = []
            errors.append(f"Deployment collection failed: {e}")

        try:
            statefulsets = self.get_workloads('StatefulSet')
        except Exception as e:
            statefulsets = []
            errors.append(f"StatefulSet collection failed: {e}")

        try:
            daemonsets = self.get_workloads('DaemonSet')
        except Exception as e:
            daemonsets = []
            errors.append(f"DaemonSet collection failed: {e}")

        try:
            services = self.get_services()
        except Exception as e:
            services = []
            errors.append(f"Service collection failed: {e}")

        try:
            hpas = self.get_hpas()
        except Exception as e:
            hpas = []
            errors.append(f"HPA collection failed: {e}")

        try:
            pvcs = self.get_pvcs()
        except Exception as e:
            pvcs = []
            errors.append(f"PVC collection failed: {e}")

        return DiagnosticSnapshot(
            namespace=self.namespace,
            context=self.context or '',
            timestamp=datetime.now().isoformat(),
            pods=pods,
            resources=resource_usage,
            events=events,
            deployments=deployments,
            statefulsets=statefulsets,
            daemonsets=daemonsets,
            services=services,
            hpas=hpas,
            pvcs=pvcs,
            errors=errors,
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _classify_pod_health(containers: List[ContainerStatus], phase: str, total_restarts: int) -> str:
        """Classify pod health: healthy, warning, critical."""
        if phase in ('Failed', 'Unknown'):
            return 'critical'

        # Check container reasons first — they indicate critical issues regardless of phase
        critical_reasons = {'CrashLoopBackOff', 'OOMKilled', 'ImagePullBackOff', 'ErrImagePull'}
        for c in containers:
            if c.reason in critical_reasons:
                return 'critical'
            if c.reason == 'Error':
                return 'critical'

        if phase == 'Pending':
            return 'warning'

        if total_restarts > 10:
            return 'warning'

        if phase == 'Succeeded':
            return 'warning'

        return 'healthy'

    @staticmethod
    def _calculate_age(start_time: str) -> str:
        """Convert ISO timestamp to human-readable age."""
        if not start_time:
            return 'unknown'
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            delta = now - dt

            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            if days > 0:
                return f"{days}d{hours}h"
            if hours > 0:
                return f"{hours}h{minutes}m"
            return f"{minutes}m"
        except (ValueError, TypeError):
            return 'unknown'


# ── Analyzer ────────────────────────────────────────────────────────────────

class DiagnosticAnalyzer:
    """Analyze diagnostic snapshot and log analysis to generate findings."""

    def analyze(
        self,
        snapshot: DiagnosticSnapshot,
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        issues = []
        recommendations = []

        # Pod health issues
        healthy_count = 0
        unhealthy_count = 0
        warning_count = 0

        for pod in snapshot.pods:
            if pod.health == 'critical':
                unhealthy_count += 1
            elif pod.health == 'warning':
                warning_count += 1
            else:
                healthy_count += 1

            for container in pod.containers:
                if container.reason == 'CrashLoopBackOff':
                    issues.append(DiagnosticIssue(
                        severity='critical',
                        source=f"pod/{pod.name}",
                        category='crashloop',
                        message=f"Container '{container.name}' is crash-looping (CrashLoopBackOff).",
                    ))
                    recommendations.append(
                        f"CrashLoopBackOff on {pod.name}/{container.name}: "
                        f"check pod logs for root cause, verify startup probe and command."
                    )

                elif container.reason == 'OOMKilled':
                    issues.append(DiagnosticIssue(
                        severity='critical',
                        source=f"pod/{pod.name}",
                        category='oom',
                        message=f"Container '{container.name}' was OOMKilled.",
                    ))
                    recommendations.append(
                        f"OOMKilled on {pod.name}/{container.name}: "
                        f"increase memory limits or investigate memory leak."
                    )

                elif container.reason in ('ImagePullBackOff', 'ErrImagePull'):
                    issues.append(DiagnosticIssue(
                        severity='critical',
                        source=f"pod/{pod.name}",
                        category='imagepull',
                        message=f"Container '{container.name}' cannot pull image: {container.reason}.",
                    ))
                    recommendations.append(
                        f"{container.reason} on {pod.name}/{container.name}: "
                        f"check image registry, credentials, or image tag/name."
                    )

                elif container.reason == 'Error':
                    issues.append(DiagnosticIssue(
                        severity='critical',
                        source=f"pod/{pod.name}",
                        category='container_error',
                        message=f"Container '{container.name}' exited with error.",
                    ))

            # High restart count
            if pod.restarts > 10:
                issues.append(DiagnosticIssue(
                    severity='warning',
                    source=f"pod/{pod.name}",
                    category='restarts',
                    message=f"Pod has {pod.restarts} restarts. Investigate stability.",
                ))
                recommendations.append(
                    f"High restart count ({pod.restarts}) on {pod.name}: "
                    f"check pod logs and events for recurring failures."
                )

            # Pending pods
            if pod.phase == 'Pending':
                issues.append(DiagnosticIssue(
                    severity='warning',
                    source=f"pod/{pod.name}",
                    category='scheduling',
                    message=f"Pod is stuck in Pending state. Reason: {', '.join(pod.conditions) if pod.conditions else 'unknown'}.",
                ))
                recommendations.append(
                    f"Pending pod {pod.name}: check node resources, PVC binding, "
                    f"or node selectors/taints."
                )

        # Resource pressure
        for ru in snapshot.resources:
            cpu_pct = self._resource_pct(ru.cpu_usage, ru.cpu_limit)
            mem_pct = self._resource_pct(ru.mem_usage, ru.mem_limit)

            if cpu_pct is not None and cpu_pct > 80:
                issues.append(DiagnosticIssue(
                    severity='warning',
                    source=f"pod/{ru.pod}",
                    category='resource',
                    message=f"CPU usage at {cpu_pct:.0f}% of limit ({ru.cpu_usage}/{ru.cpu_limit}).",
                ))
                recommendations.append(
                    f"High CPU on {ru.pod} ({cpu_pct:.0f}% of limit): "
                    f"consider increasing CPU limit or scaling horizontally."
                )

            if mem_pct is not None and mem_pct > 80:
                issues.append(DiagnosticIssue(
                    severity='warning',
                    source=f"pod/{ru.pod}",
                    category='resource',
                    message=f"Memory usage at {mem_pct:.0f}% of limit ({ru.mem_usage}/{ru.mem_limit}).",
                ))
                recommendations.append(
                    f"High memory on {ru.pod} ({mem_pct:.0f}% of limit): "
                    f"risk of OOM. Increase memory limit or investigate."
                )

        # Workload readiness
        for wl in snapshot.deployments + snapshot.statefulsets + snapshot.daemonsets:
            if wl.available < wl.desired and wl.desired > 0:
                severity = 'critical' if wl.available == 0 else 'warning'
                issues.append(DiagnosticIssue(
                    severity=severity,
                    source=f"{wl.kind.lower()}/{wl.name}",
                    category='readiness',
                    message=f"{wl.kind} {wl.name} has {wl.ready} ready replicas (desired: {wl.desired}).",
                ))
                recommendations.append(
                    f"{wl.kind} {wl.name} not fully ready ({wl.ready}/{wl.desired}): "
                    f"check pod status and events in namespace."
                )

        # Warning events
        warning_events = [e for e in snapshot.events if e.type == 'Warning']
        if len(warning_events) > 0:
            if len(warning_events) > 10:
                issues.append(DiagnosticIssue(
                    severity='warning',
                    source=f"namespace/{snapshot.namespace}",
                    category='events',
                    message=f"{len(warning_events)} warning events in namespace.",
                ))

        # Log-based issues
        log_summary = {}
        if log_analysis:
            log_summary = log_analysis.get('summary', {})
            total_logs = log_summary.get('total', 0)
            log_errors = log_summary.get('errors', 0) or log_summary.get('error', 0)

            if total_logs > 0 and log_errors > total_logs * 0.1:
                issues.append(DiagnosticIssue(
                    severity='warning',
                    source=f"namespace/{snapshot.namespace}",
                    category='log_errors',
                    message=f"High error rate in logs: {log_errors}/{total_logs} entries are errors.",
                ))
                recommendations.append(
                    "High log error rate detected. Review Top Errors in log analysis section."
                )

        return {
            'snapshot': snapshot,
            'issues': issues,
            'recommendations': recommendations,
            'pod_summary': {
                'total': len(snapshot.pods),
                'healthy': healthy_count,
                'unhealthy': unhealthy_count,
                'warning': warning_count,
            },
            'event_summary': {
                'total': len(snapshot.events),
                'warnings': len(warning_events),
            },
            'log_summary': log_summary,
        }

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _resource_pct(usage: str, limit: str) -> Optional[float]:
        """Calculate resource usage as percentage of limit. Returns None if not computable."""
        if not usage or not limit or usage == 'N/A' or limit == 'N/A':
            return None

        try:
            usage_m = DiagnosticAnalyzer._parse_resource(usage)
            limit_m = DiagnosticAnalyzer._parse_resource(limit)
            if limit_m > 0:
                return (usage_m / limit_m) * 100
            return None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_resource(value: str) -> float:
        """Parse K8s resource string to base units (millicores for CPU, Mi for memory)."""
        value = value.strip()
        if not value or value == '0':
            return 0.0

        # Memory: Ki, Mi, Gi, Ti
        if value.endswith('Ki'):
            return float(value[:-2]) / 1024  # Convert to Mi
        elif value.endswith('Mi'):
            return float(value[:-2])
        elif value.endswith('Gi'):
            return float(value[:-2]) * 1024
        elif value.endswith('Ti'):
            return float(value[:-2]) * 1024 * 1024
        # CPU: n, u (micro), m (milli)
        elif value.endswith('m'):
            return float(value[:-1])
        elif value.endswith('n'):
            return float(value[:-1]) / 1_000_000
        elif value.endswith('u'):
            return float(value[:-1]) / 1_000
        else:
            # Plain number (CPU cores as float)
            try:
                return float(value) * 1000  # Convert cores to millicores
            except ValueError:
                return 0.0
