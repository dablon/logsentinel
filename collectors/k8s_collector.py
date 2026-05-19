"""
Collectors for various log sources: Kubernetes, Syslog, Journald.
"""
import subprocess
from typing import List, Optional


class K8sCollector:
    """Collect logs from Kubernetes pods/containers using kubectl."""

    def __init__(self, namespace: Optional[str] = None, context: Optional[str] = None):
        self.namespace = namespace
        self.context = context

    def _base_args(self) -> List[str]:
        args = ['kubectl']
        if self.context:
            args += ['--context', self.context]
        return args

    def list_pods(self) -> List[str]:
        """Return pod names in the configured namespace (or all namespaces if namespace is None)."""
        cmd = self._base_args() + ['get', 'pods', '-o', 'jsonpath={.items[*].metadata.name}']
        if self.namespace:
            cmd += ['-n', self.namespace]
        elif self.namespace is None:
            cmd += ['--all-namespaces']
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
            )
            output = result.stdout.strip() if result.stdout else ''
            return output.split() if output else []
        except subprocess.TimeoutExpired:
            print(f"Timeout listing pods in namespace {self.namespace}")
            return []
        except FileNotFoundError:
            print("kubectl not available")
            return []
        except Exception as e:
            print(f"Error listing kubernetes pods: {e}")
            return []

    def get_pod_logs(
        self,
        pod: str,
        container: Optional[str] = None,
        lines: int = 100,
        previous: bool = False,
    ) -> List[str]:
        """Return log lines for a specific pod (and optionally a container)."""
        cmd = self._base_args() + ['logs', pod, '--tail', str(lines)]
        if self.namespace:
            cmd += ['-n', self.namespace]
        if container:
            cmd += ['-c', container]
        if previous:
            cmd += ['--previous']
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return [line for line in result.stdout.split('\n') if line]
            return []
        except subprocess.TimeoutExpired:
            print(f"Timeout getting logs from pod {pod}")
            return []
        except FileNotFoundError:
            print("kubectl not available")
            return []
        except Exception as e:
            print(f"Error getting kubernetes logs: {e}")
            return []

    def get_all_pod_logs(self, lines: int = 100) -> dict:
        """Return a dict mapping pod name to list of log lines for all pods."""
        pods = self.list_pods()
        return {pod: self.get_pod_logs(pod, lines=lines) for pod in pods}

    def get_namespace_logs(
        self,
        lines: int = 100,
        container: Optional[str] = None,
    ) -> dict:
        """
        Smart namespace log collection.

        Reads logs from all pods in the namespace while keeping total volume near
        the requested `lines` budget by splitting lines across discovered pods.
        If a pod has no current logs, a best-effort attempt is made to read
        previous container logs.
        """
        pods = self.list_pods()
        if not pods:
            return {}

        per_pod_lines = max(1, lines // len(pods))
        namespace_logs = {}
        for pod in pods:
            pod_logs = self.get_pod_logs(pod, container=container, lines=per_pod_lines)
            if not pod_logs:
                pod_logs = self.get_pod_logs(
                    pod,
                    container=container,
                    lines=per_pod_lines,
                    previous=True,
                )
            namespace_logs[pod] = pod_logs
        return namespace_logs


class SyslogCollector:
    """Collect logs from a syslog file."""

    def __init__(self, log_file: str = '/var/log/syslog'):
        self.log_file = log_file

    def read_logs(self, lines: int = 100) -> List[str]:
        """Return last *lines* lines from the syslog file."""
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
            return [line.rstrip('\n') for line in all_lines[-lines:] if line.strip()]
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"Error reading syslog {self.log_file}: {e}")
            return []


class JournaldCollector:
    """Collect logs from systemd journal via journalctl."""

    def __init__(self, unit: Optional[str] = None):
        self.unit = unit

    def get_logs(self, lines: int = 100) -> List[str]:
        """Return last *lines* journal entries."""
        cmd = ['journalctl', '-n', str(lines), '--no-pager', '--output=short']
        if self.unit:
            cmd += ['-u', self.unit]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
            )
            if result.returncode == 0 and result.stdout:
                return [line for line in result.stdout.split('\n') if line]
            return []
        except subprocess.TimeoutExpired:
            print("Timeout reading journald logs")
            return []
        except FileNotFoundError:
            # journalctl not available
            return []
        except Exception as e:
            print(f"Error reading journald: {e}")
            return []
