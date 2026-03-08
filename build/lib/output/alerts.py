"""
Alert rules and notification manager for log analysis results.
"""
from typing import Dict, List


class AlertManager:
    """Check analysis results against configurable rules and raise alerts."""

    DEFAULT_RULES = [
        {
            'name': 'high_error_count',
            'condition': lambda s: s.get('summary', {}).get('error', 0) > 10,
            'message': 'High error volume detected',
            'severity': 'critical',
        },
        {
            'name': 'high_warning_count',
            'condition': lambda s: s.get('summary', {}).get('warning', 0) > 20,
            'message': 'Many warnings present',
            'severity': 'warning',
        },
        {
            'name': 'repeated_error_pattern',
            'condition': lambda s: any(
                p.get('count', 0) >= 5
                for p in s.get('analysis', {}).get('error_patterns', [])
            ),
            'message': 'Repeated error pattern detected',
            'severity': 'high',
        },
    ]

    def __init__(self, rules: List[Dict] = None):
        self.rules = rules if rules is not None else list(self.DEFAULT_RULES)
        self._notification_handlers = []

    def add_notification_handler(self, handler):
        """Register a callable that receives (alert, analysis)."""
        self._notification_handlers.append(handler)

    def check(self, analysis: Dict) -> List[Dict]:
        """Evaluate all rules against *analysis* and return triggered alerts."""
        alerts = []
        for rule in self.rules:
            try:
                if rule['condition'](analysis):
                    alerts.append({
                        'name': rule['name'],
                        'message': rule['message'],
                        'severity': rule['severity'],
                    })
            except Exception as e:
                print(f"Alert rule '{rule.get('name', 'unknown')}' evaluation failed: {e}")
        return alerts

    def send_alerts(self, alerts: List[Dict], analysis: Dict):
        """Dispatch triggered alerts to all registered notification handlers."""
        for alert in alerts:
            for handler in self._notification_handlers:
                try:
                    handler(alert, analysis)
                except Exception as e:
                    print(f"Notification handler error: {e}")
