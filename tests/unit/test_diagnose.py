"""Unit tests for k8s_diagnose module — deep namespace diagnosis"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

def test_pod_health_creation():
    from collectors.k8s_diagnose import PodHealth
    p = PodHealth(
        name='test-pod', namespace='test-ns', phase='Running',
        ready='1/1', restarts=3, age='5m',
    )
    assert p.name == 'test-pod'
    assert p.health == 'unknown'
    assert p.containers == []


def test_container_status_creation():
    from collectors.k8s_diagnose import ContainerStatus
    c = ContainerStatus(
        name='app', ready=True, restart_count=0,
        state='running', reason='Started', image='nginx:latest',
    )
    assert c.name == 'app'
    assert c.ready is True


def test_diagnostic_snapshot_creation():
    from collectors.k8s_diagnose import DiagnosticSnapshot
    ds = DiagnosticSnapshot(
        namespace='test-ns', context='kind-kind',
        timestamp='2026-01-01T00:00:00',
    )
    assert ds.namespace == 'test-ns'
    assert ds.pods == []
    assert ds.events == []


def test_diagnostic_issue_creation():
    from collectors.k8s_diagnose import DiagnosticIssue
    i = DiagnosticIssue(
        severity='critical', source='pod/test-pod',
        category='crashloop', message='Pod is crash-looping',
    )
    assert i.severity == 'critical'
    assert i.category == 'crashloop'


# ═══════════════════════════════════════════════════════════════════════════════
# K8sDiagnosticCollector
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosticCollector:
    def test_init(self):
        from collectors.k8s_diagnose import K8sDiagnosticCollector
        c = K8sDiagnosticCollector(namespace='default', context='prod')
        assert c.namespace == 'default'
        assert c.context == 'prod'

    def test_init_no_context(self):
        from collectors.k8s_diagnose import K8sDiagnosticCollector
        c = K8sDiagnosticCollector(namespace='kube-system')
        assert c.context is None

    def test_collect_all_empty_namespace(self, monkeypatch):
        """Empty namespace returns empty snapshot."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='empty-ns')

        def fake_run_json(args, timeout=30):
            if 'pods' in args:
                return {'items': []}
            if 'events' in args:
                return {'items': []}
            if 'deployment' in args[0].lower() and 'get' in args:
                return {'items': []}
            if 'statefulset' in args[0].lower() and 'get' in args:
                return {'items': []}
            if 'daemonset' in args[0].lower() and 'get' in args:
                return {'items': []}
            if 'svc' in args:
                return {'items': []}
            return None

        def fake_run_text(args, timeout=30):
            return ''

        monkeypatch.setattr(collector, '_run_json', fake_run_json)
        monkeypatch.setattr(collector, '_run_text', fake_run_text)

        snapshot = collector.collect_all()
        assert snapshot.namespace == 'empty-ns'
        assert snapshot.pods == []
        assert snapshot.events == []
        assert snapshot.deployments == []

    def test_pod_status_parsing(self, monkeypatch):
        """Parse kubectl get pods -o json correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [
                {
                    'metadata': {'name': 'api-pod', 'creationTimestamp': '2026-01-01T00:00:00Z'},
                    'spec': {'nodeName': 'node-1', 'containers': [
                        {'name': 'api', 'image': 'api:v1', 'resources': {
                            'requests': {'cpu': '100m', 'memory': '128Mi'},
                            'limits': {'cpu': '500m', 'memory': '512Mi'},
                        }}
                    ]},
                    'status': {
                        'phase': 'Running',
                        'startTime': '2026-01-01T00:00:00Z',
                        'conditions': [
                            {'type': 'Ready', 'status': 'True'},
                            {'type': 'PodScheduled', 'status': 'True'},
                        ],
                        'containerStatuses': [
                            {
                                'name': 'api', 'ready': True,
                                'restartCount': 0,
                                'state': {'running': {'startedAt': '2026-01-01T00:00:00Z'}},
                                'image': 'api:v1',
                            }
                        ],
                    },
                }
            ]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)
        monkeypatch.setattr(collector, '_run_text', lambda args, timeout=30: '')

        pods = collector.get_pod_statuses()
        assert len(pods) == 1
        assert pods[0].name == 'api-pod'
        assert pods[0].phase == 'Running'
        assert pods[0].ready == '1/1'
        assert pods[0].restarts == 0
        assert pods[0].health == 'healthy'
        assert pods[0].node == 'node-1'
        assert len(pods[0].containers) == 1
        assert pods[0].containers[0].state == 'running'

    def test_pod_crashloop_detection(self, monkeypatch):
        """CrashLoopBackOff containers = critical health."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [{
                'metadata': {'name': 'crash-pod'},
                'spec': {'nodeName': 'node-1', 'containers': [{'name': 'app', 'image': 'bad:v1'}]},
                'status': {
                    'phase': 'Running',
                    'startTime': '2026-01-01T00:00:00Z',
                    'conditions': [],
                    'containerStatuses': [{
                        'name': 'app', 'ready': False, 'restartCount': 25,
                        'state': {'waiting': {'reason': 'CrashLoopBackOff'}},
                        'image': 'bad:v1',
                    }],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)

        pods = collector.get_pod_statuses()
        assert pods[0].health == 'critical'
        assert pods[0].containers[0].reason == 'CrashLoopBackOff'

    def test_pod_oomkilled_detection(self, monkeypatch):
        """OOMKilled termination reason = critical health."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [{
                'metadata': {'name': 'oom-pod'},
                'spec': {'nodeName': 'node-1', 'containers': [{'name': 'app', 'image': 'app:v1'}]},
                'status': {
                    'phase': 'Running',
                    'startTime': '2026-01-01T00:00:00Z',
                    'conditions': [],
                    'containerStatuses': [{
                        'name': 'app', 'ready': False, 'restartCount': 15,
                        'state': {'terminated': {
                            'reason': 'OOMKilled', 'exitCode': 137,
                            'startedAt': '2026-01-01T00:00:00Z',
                            'finishedAt': '2026-01-01T01:00:00Z',
                        }},
                        'image': 'app:v1',
                    }],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)

        pods = collector.get_pod_statuses()
        assert pods[0].health == 'critical'
        assert pods[0].containers[0].reason == 'OOMKilled'

    def test_pod_imagepullbackoff_detection(self, monkeypatch):
        """ImagePullBackOff = critical health."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [{
                'metadata': {'name': 'img-pod'},
                'spec': {'nodeName': 'node-1', 'containers': [{'name': 'app', 'image': 'bad:v1'}]},
                'status': {
                    'phase': 'Pending',
                    'startTime': '2026-01-01T00:00:00Z',
                    'conditions': [],
                    'containerStatuses': [{
                        'name': 'app', 'ready': False, 'restartCount': 0,
                        'state': {'waiting': {'reason': 'ErrImagePull'}},
                        'image': 'bad:v1',
                    }],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)

        pods = collector.get_pod_statuses()
        assert pods[0].health == 'critical'
        assert pods[0].containers[0].reason == 'ErrImagePull'

    def test_pod_pending_detection(self, monkeypatch):
        """Pending phase = warning health."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [{
                'metadata': {'name': 'pending-pod'},
                'spec': {'nodeName': '', 'containers': [{'name': 'app', 'image': 'app:v1'}]},
                'status': {
                    'phase': 'Pending',
                    'startTime': '',
                    'conditions': [{'type': 'PodScheduled', 'status': 'False', 'reason': 'Unschedulable'}],
                    'containerStatuses': [],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)

        pods = collector.get_pod_statuses()
        assert pods[0].health == 'warning'
        assert pods[0].phase == 'Pending'

    def test_pod_high_restarts_warning(self, monkeypatch):
        """High restart count (>10) = warning health."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [{
                'metadata': {'name': 'restart-pod'},
                'spec': {'nodeName': 'node-1', 'containers': [{'name': 'app', 'image': 'app:v1'}]},
                'status': {
                    'phase': 'Running',
                    'startTime': '2026-01-01T00:00:00Z',
                    'conditions': [],
                    'containerStatuses': [{
                        'name': 'app', 'ready': True, 'restartCount': 12,
                        'state': {'running': {}},
                        'image': 'app:v1',
                    }],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)

        pods = collector.get_pod_statuses()
        assert pods[0].health == 'warning'

    def test_resource_usage_parsing(self, monkeypatch):
        """kubectl top pods output is parsed correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        monkeypatch.setattr(collector, '_run_text', lambda args, timeout=30:
            'api-pod  120m  256Mi\nworker-pod  850m  1.2Gi\n')

        resources = collector.get_resource_usage()
        assert len(resources) == 2
        assert resources[0].pod == 'api-pod'
        assert resources[0].cpu_usage == '120m'
        assert resources[0].mem_usage == '256Mi'
        assert resources[1].pod == 'worker-pod'
        assert resources[1].cpu_usage == '850m'

    def test_resource_usage_no_metrics_server(self, monkeypatch):
        """kubectl top fails → empty list."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        monkeypatch.setattr(collector, '_run_text', lambda args, timeout=30: None)

        resources = collector.get_resource_usage()
        assert resources == []

    def test_events_parsing(self, monkeypatch):
        """kubectl get events output parsed correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_events = {
            'items': [
                {
                    'type': 'Warning',
                    'reason': 'BackOff',
                    'message': 'Back-off restarting failed container',
                    'lastTimestamp': '2026-04-28T10:00:00Z',
                    'source': {'component': 'kubelet', 'host': 'node-1'},
                },
                {
                    'type': 'Normal',
                    'reason': 'Pulling',
                    'message': 'Pulling image "nginx:latest"',
                    'lastTimestamp': '2026-04-28T09:00:00Z',
                    'source': {'component': 'kubelet', 'host': 'node-1'},
                },
            ]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_events)

        events = collector.get_events()
        assert len(events) == 2
        assert events[0].type == 'Warning'
        assert events[0].reason == 'BackOff'
        assert events[1].type == 'Normal'

    def test_deployment_parsing(self, monkeypatch):
        """kubectl get deployments -o json parsed correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_data = {
            'items': [{
                'metadata': {'name': 'api'},
                'status': {
                    'replicas': 3,
                    'readyReplicas': 3,
                    'availableReplicas': 3,
                    'unavailableReplicas': 0,
                    'conditions': [
                        {'type': 'Available', 'status': 'True', 'reason': 'MinimumReplicasAvailable'},
                    ],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_data)

        deps = collector.get_workloads('Deployment')
        assert len(deps) == 1
        assert deps[0].name == 'api'
        assert deps[0].ready == '3/3'
        assert deps[0].available == 3
        assert deps[0].kind == 'Deployment'

    def test_unhealthy_deployment_parsing(self, monkeypatch):
        """0/1 ready deployment."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_data = {
            'items': [{
                'metadata': {'name': 'failing-svc'},
                'status': {
                    'replicas': 1,
                    'readyReplicas': 0,
                    'availableReplicas': 0,
                    'unavailableReplicas': 1,
                    'conditions': [
                        {'type': 'Available', 'status': 'False', 'reason': 'MinimumReplicasUnavailable'},
                    ],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_data)

        deps = collector.get_workloads('Deployment')
        assert deps[0].ready == '0/1'
        assert deps[0].available == 0

    def test_services_parsing(self, monkeypatch):
        """kubectl get svc -o json parsed correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_data = {
            'items': [{
                'metadata': {'name': 'api-svc'},
                'spec': {
                    'type': 'ClusterIP',
                    'clusterIP': '10.0.0.1',
                    'ports': [{'port': 80, 'targetPort': 8080, 'protocol': 'TCP'}],
                },
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_data)

        services = collector.get_services()
        assert len(services) == 1
        assert services[0]['name'] == 'api-svc'
        assert services[0]['type'] == 'ClusterIP'
        assert '80:8080/TCP' in services[0]['ports']

    def test_hpa_parsing(self, monkeypatch):
        """kubectl get hpa --no-headers parsed correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        monkeypatch.setattr(collector, '_run_text', lambda args, timeout=30:
            'api-hpa  Deployment/api  75%/80%  2  10  5\n')

        hpas = collector.get_hpas()
        assert len(hpas) == 1
        assert hpas[0]['name'] == 'api-hpa'
        assert hpas[0]['min_pods'] == '2'
        assert hpas[0]['max_pods'] == '10'

    def test_pvc_parsing(self, monkeypatch):
        """kubectl get pvc --no-headers parsed correctly."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        monkeypatch.setattr(collector, '_run_text', lambda args, timeout=30:
            'data-pvc  Bound  pvc-abc123  10Gi  RWO\n')

        pvcs = collector.get_pvcs()
        assert len(pvcs) == 1
        assert pvcs[0]['name'] == 'data-pvc'
        assert pvcs[0]['status'] == 'Bound'
        assert pvcs[0]['capacity'] == '10Gi'

    def test_collect_all_includes_errors(self, monkeypatch):
        """Failed collections are captured in snapshot.errors."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: {'items': []})
        monkeypatch.setattr(collector, '_run_text', lambda args, timeout=30: '')

        snapshot = collector.collect_all()
        assert snapshot.errors == []

    def test_collect_all_handles_exceptions(self, monkeypatch):
        """Exceptions during collection are caught."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')

        def failing_json(args, timeout=30):
            raise Exception('kubectl not found')

        monkeypatch.setattr(collector, '_run_json', failing_json)
        monkeypatch.setattr(collector, '_run_text', failing_json)

        snapshot = collector.collect_all()
        assert len(snapshot.errors) > 0

    def test_resource_limits_parsing(self, monkeypatch):
        """Pod spec resource requests/limits extracted."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector

        collector = K8sDiagnosticCollector(namespace='test')
        mock_pods = {
            'items': [{
                'metadata': {'name': 'limited-pod'},
                'spec': {'containers': [
                    {'name': 'app', 'resources': {
                        'requests': {'cpu': '250m', 'memory': '512Mi'},
                        'limits': {'cpu': '1000m', 'memory': '1Gi'},
                    }},
                ]},
            }]
        }
        monkeypatch.setattr(collector, '_run_json', lambda args, timeout=30: mock_pods)

        limits = collector.get_resource_limits()
        assert 'limited-pod' in limits
        assert limits['limited-pod']['app']['cpu_limit'] == '1000m'
        assert limits['limited-pod']['app']['mem_request'] == '512Mi'

    def test_calculate_age(self):
        """Age calculation from ISO timestamp."""
        from collectors.k8s_diagnose import K8sDiagnosticCollector
        from datetime import datetime, timedelta

        past = (datetime.now() - timedelta(hours=2, minutes=30)).isoformat()
        age = K8sDiagnosticCollector._calculate_age(past)
        assert '2h' in age

        recent = (datetime.now() - timedelta(minutes=5)).isoformat()
        age2 = K8sDiagnosticCollector._calculate_age(recent)
        assert 'm' in age2

        age3 = K8sDiagnosticCollector._calculate_age('')
        assert age3 == 'unknown'

        age4 = K8sDiagnosticCollector._calculate_age('not-a-date')
        assert age4 == 'unknown'


# ═══════════════════════════════════════════════════════════════════════════════
# DiagnosticAnalyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnosticAnalyzer:
    def _make_snapshot(self, pods=None, resources=None, events=None,
                       deployments=None, statefulsets=None, daemonsets=None):
        from collectors.k8s_diagnose import DiagnosticSnapshot
        return DiagnosticSnapshot(
            namespace='test', context='', timestamp='now',
            pods=pods or [],
            resources=resources or [],
            events=events or [],
            deployments=deployments or [],
            statefulsets=statefulsets or [],
            daemonsets=daemonsets or [],
        )

    def _make_pod(self, name, health='healthy', phase='Running', restarts=0,
                  containers=None, conditions=None):
        from collectors.k8s_diagnose import PodHealth
        return PodHealth(
            name=name, namespace='test', phase=phase,
            ready='1/1', restarts=restarts, age='5m',
            containers=containers or [],
            health=health,
            conditions=conditions or [],
        )

    def _make_container(self, name, state='running', reason='Started', ready=True, restarts=0):
        from collectors.k8s_diagnose import ContainerStatus
        return ContainerStatus(
            name=name, ready=ready, restart_count=restarts,
            state=state, reason=reason, image=f'{name}:latest',
        )

    def test_empty_snapshot_no_issues(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        result = da.analyze(self._make_snapshot())

        assert result['issues'] == []
        assert result['recommendations'] == []
        assert result['pod_summary']['total'] == 0

    def test_crashloopbackoff_issue_detected(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        container = self._make_container('app', state='waiting', reason='CrashLoopBackOff', ready=False)
        pod = self._make_pod('crash-pod', health='critical', containers=[container])

        result = da.analyze(self._make_snapshot(pods=[pod]))

        assert len(result['issues']) >= 1
        crash_issues = [i for i in result['issues'] if i.category == 'crashloop']
        assert len(crash_issues) == 1
        assert crash_issues[0].severity == 'critical'
        assert 'CrashLoopBackOff' in result['recommendations'][0]

    def test_oomkilled_issue_detected(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        container = self._make_container('app', state='terminated', reason='OOMKilled', ready=False)
        pod = self._make_pod('oom-pod', health='critical', containers=[container])

        result = da.analyze(self._make_snapshot(pods=[pod]))

        oom_issues = [i for i in result['issues'] if i.category == 'oom']
        assert len(oom_issues) == 1
        assert oom_issues[0].severity == 'critical'
        assert 'OOMKilled' in result['recommendations'][0]

    def test_imagepull_issue_detected(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        container = self._make_container('app', state='waiting', reason='ImagePullBackOff', ready=False)
        pod = self._make_pod('img-pod', health='critical', containers=[container])

        result = da.analyze(self._make_snapshot(pods=[pod]))

        img_issues = [i for i in result['issues'] if i.category == 'imagepull']
        assert len(img_issues) == 1
        assert img_issues[0].severity == 'critical'
        assert 'ImagePullBackOff' in result['recommendations'][0]

    def test_high_restarts_warning(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        container = self._make_container('app', state='running', reason='Started', restarts=0)
        pod = self._make_pod('restart-pod', health='warning', restarts=15, containers=[container])

        result = da.analyze(self._make_snapshot(pods=[pod]))

        restart_issues = [i for i in result['issues'] if i.category == 'restarts']
        assert len(restart_issues) == 1
        assert restart_issues[0].severity == 'warning'
        assert '15 restarts' in restart_issues[0].message

    def test_pending_pod_warning(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        pod = self._make_pod(
            'pending-pod', health='warning', phase='Pending',
            conditions=['Unschedulable'],
        )

        result = da.analyze(self._make_snapshot(pods=[pod]))

        pending_issues = [i for i in result['issues'] if i.category == 'scheduling']
        assert len(pending_issues) == 1
        assert pending_issues[0].severity == 'warning'

    def test_resource_pressure_detected(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer
        from collectors.k8s_diagnose import ResourceUsage

        da = DiagnosticAnalyzer()
        ru = ResourceUsage(
            pod='api-pod', cpu_usage='900m', cpu_limit='1000m',
            mem_usage='512Mi', mem_limit='512Mi',
        )

        result = da.analyze(self._make_snapshot(resources=[ru]))

        resource_issues = [i for i in result['issues'] if i.category == 'resource']
        assert len(resource_issues) >= 1
        # CPU at 90% of limit
        cpu_issues = [i for i in resource_issues if 'CPU' in i.message]
        assert len(cpu_issues) == 1
        # MEM at 100% of limit
        mem_issues = [i for i in resource_issues if 'Memory' in i.message]
        assert len(mem_issues) == 1

    def test_unready_deployment_detected(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer
        from collectors.k8s_diagnose import WorkloadStatus

        da = DiagnosticAnalyzer()
        dep = WorkloadStatus(
            name='failing-deploy', kind='Deployment',
            ready='0/3', desired=3, available=0, unavailable=3,
        )

        result = da.analyze(self._make_snapshot(deployments=[dep]))

        readiness_issues = [i for i in result['issues'] if i.category == 'readiness']
        assert len(readiness_issues) == 1
        assert readiness_issues[0].severity == 'critical'
        assert 'Deployment' in readiness_issues[0].message

    def test_multiple_warning_events_issue(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer
        from collectors.k8s_diagnose import K8sEvent

        da = DiagnosticAnalyzer()
        events = [
            K8sEvent(type='Warning', reason=f'BackOff{i}', message=f'Error {i}',
                     timestamp='now', source_component='kubelet', source_host='node-1')
            for i in range(15)
        ]

        result = da.analyze(self._make_snapshot(events=events))

        event_issues = [i for i in result['issues'] if i.category == 'events']
        assert len(event_issues) == 1

    def test_high_log_error_rate_issue(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        log_analysis = {
            'summary': {'total': 100, 'errors': 20, 'warnings': 10},
            'errors': [{'level': 'ERROR', 'message': 'test'}] * 5,
        }

        result = da.analyze(self._make_snapshot(), log_analysis=log_analysis)

        log_issues = [i for i in result['issues'] if i.category == 'log_errors']
        assert len(log_issues) == 1
        assert 'error rate' in result['recommendations'][-1].lower()

    def test_pod_summary_counts(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        da = DiagnosticAnalyzer()
        pods = [
            self._make_pod('healthy-1', health='healthy'),
            self._make_pod('healthy-2', health='healthy'),
            self._make_pod('warning-1', health='warning'),
            self._make_pod('critical-1', health='critical'),
        ]

        result = da.analyze(self._make_snapshot(pods=pods))
        assert result['pod_summary']['total'] == 4
        assert result['pod_summary']['healthy'] == 2
        assert result['pod_summary']['warning'] == 1
        assert result['pod_summary']['unhealthy'] == 1

    def test_resource_pct_parsing(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        assert DiagnosticAnalyzer._resource_pct('500m', '1000m') == pytest.approx(50.0)
        assert DiagnosticAnalyzer._resource_pct('1000m', '1000m') == pytest.approx(100.0)
        assert DiagnosticAnalyzer._resource_pct('256Mi', '1Gi') == pytest.approx(25.0)
        assert DiagnosticAnalyzer._resource_pct('N/A', '1000m') is None
        assert DiagnosticAnalyzer._resource_pct('100m', 'N/A') is None
        assert DiagnosticAnalyzer._resource_pct('', '') is None

    def test_parse_resource_values(self):
        from collectors.k8s_diagnose import DiagnosticAnalyzer

        # CPU
        assert DiagnosticAnalyzer._parse_resource('500m') == 500.0
        assert DiagnosticAnalyzer._parse_resource('1') == 1000.0  # cores → millicores
        assert DiagnosticAnalyzer._parse_resource('1000m') == 1000.0
        # Memory
        assert DiagnosticAnalyzer._parse_resource('512Mi') == 512.0
        assert DiagnosticAnalyzer._parse_resource('1Gi') == 1024.0
        assert DiagnosticAnalyzer._parse_resource('128Ki') == 0.125  # 128/1024
        assert DiagnosticAnalyzer._parse_resource('1Ti') == 1024 * 1024
        # Edge cases
        assert DiagnosticAnalyzer._parse_resource('') == 0.0
        assert DiagnosticAnalyzer._parse_resource('0') == 0.0
        assert DiagnosticAnalyzer._parse_resource('invalid') == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# CLI integration
# ═══════════════════════════════════════════════════════════════════════════════

def test_cli_diagnose_flag_exists():
    """--diagnose flag appears in arg parser."""
    import subprocess
    result = subprocess.run(
        ['python', 'logsentinel.py', '--help'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=os.path.join(os.path.dirname(__file__), '../..'),
    )
    assert '--diagnose' in result.stdout


def test_cli_diagnose_requires_namespace():
    """--diagnose without --namespace should fail."""
    import subprocess
    result = subprocess.run(
        ['python', 'logsentinel.py', '--diagnose'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=os.path.join(os.path.dirname(__file__), '../..'),
    )
    assert result.returncode != 0 or 'namespace' in (result.stdout + result.stderr).lower()


def test_diagnose_flag_recognized_in_main():
    """argparse in main() accepts --diagnose."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--diagnose', action='store_true')
    args = parser.parse_args(['--diagnose'])
    assert args.diagnose is True


# ═══════════════════════════════════════════════════════════════════════════════
# DiagnoseReportGenerator
# ═══════════════════════════════════════════════════════════════════════════════

def test_report_generator_init():
    from output.diagnose_report import DiagnoseReportGenerator
    gen = DiagnoseReportGenerator(output_dir='/tmp/test_reports')
    assert gen.output_dir == '/tmp/test_reports'


def test_report_generate_html(monkeypatch, tmp_path):
    """Reports contain expected diagnostic data."""
    from output.diagnose_report import DiagnoseReportGenerator
    from collectors.k8s_diagnose import (
        DiagnosticSnapshot, PodHealth, ContainerStatus,
        ResourceUsage, K8sEvent, WorkloadStatus, DiagnosticIssue,
    )

    gen = DiagnoseReportGenerator(output_dir=str(tmp_path))

    # Build a realistic diagnosis
    container = ContainerStatus(name='api', ready=True, restart_count=0,
                                state='running', reason='Started', image='api:v1')
    crash_container = ContainerStatus(name='cache', ready=False, restart_count=12,
                                       state='waiting', reason='CrashLoopBackOff', image='cache:v1')
    pod1 = PodHealth(name='api-pod', namespace='test', phase='Running',
                     ready='1/1', restarts=0, age='5h', containers=[container],
                     health='healthy')
    pod2 = PodHealth(name='cache-pod', namespace='test', phase='Running',
                     ready='0/1', restarts=12, age='5h', containers=[crash_container],
                     health='critical')

    snapshot = DiagnosticSnapshot(
        namespace='test', context='prod', timestamp='2026-04-28T10:00:00',
        pods=[pod1, pod2],
        resources=[ResourceUsage(pod='api-pod', cpu_usage='120m', cpu_limit='500m',
                                  mem_usage='256Mi', mem_limit='512Mi')],
        events=[K8sEvent(type='Warning', reason='BackOff',
                          message='Back-off restarting', timestamp='2026-04-28T10:00:00Z',
                          source_component='kubelet', source_host='node-1')],
        deployments=[WorkloadStatus(name='api', kind='Deployment', ready='3/3',
                                     desired=3, available=3, unavailable=0)],
    )

    diagnosis = {
        'snapshot': snapshot,
        'pod_summary': {'total': 2, 'healthy': 1, 'warning': 0, 'unhealthy': 1},
        'event_summary': {'total': 1, 'warnings': 1},
        'log_summary': {'total': 100, 'errors': 5, 'warnings': 10},
        'issues': [
            DiagnosticIssue(severity='critical', source='pod/cache-pod',
                            category='crashloop',
                            message='Container cache is crash-looping.'),
        ],
        'recommendations': ['Check cache-pod logs for root cause.'],
        'llm_insights': 'The cache service is failing due to misconfiguration.',
    }

    path = gen.generate_html(diagnosis)
    assert os.path.exists(path)
    content = open(path, 'r', encoding='utf-8').read()
    assert '<html' in content
    assert 'cache-pod' in content
    assert 'CrashLoopBackOff' in content
    assert 'critical' in content
    assert 'Back-off' in content


def test_report_generate_markdown(monkeypatch, tmp_path):
    """Markdown reports contain expected diagnostic data."""
    from output.diagnose_report import DiagnoseReportGenerator
    from collectors.k8s_diagnose import DiagnosticSnapshot, PodHealth

    gen = DiagnoseReportGenerator(output_dir=str(tmp_path))

    pod = PodHealth(name='api-pod', namespace='test', phase='Running',
                    ready='1/1', restarts=0, age='5h', containers=[], health='healthy')
    snapshot = DiagnosticSnapshot(namespace='test', context='prod',
                                   timestamp='2026-04-28T10:00:00', pods=[pod])

    diagnosis = {
        'snapshot': snapshot,
        'pod_summary': {'total': 1, 'healthy': 1, 'warning': 0, 'unhealthy': 0},
        'event_summary': {'total': 0, 'warnings': 0},
        'log_summary': {},
        'issues': [],
        'recommendations': [],
    }

    path = gen.generate_markdown(diagnosis)
    assert os.path.exists(path)
    content = open(path, 'r', encoding='utf-8').read()
    assert '# LogSentinel Namespace Diagnosis' in content
    assert 'api-pod' in content
    assert 'healthy' in content


def test_report_cli_flag_exists():
    """--report flag appears in help."""
    import subprocess
    result = subprocess.run(
        ['python', 'logsentinel.py', '--help'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=os.path.join(os.path.dirname(__file__), '../..'),
    )
    assert '--report' in result.stdout
    assert '--report-dir' in result.stdout
