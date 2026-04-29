"""
Report generator for namespace diagnosis results.
Produces HTML (primary), Markdown, and optionally PDF reports.
"""
import html as _html
import os
from datetime import datetime
from typing import Dict, Optional


class DiagnoseReportGenerator:
    """Generate diagnostic reports from DiagnosticAnalyzer output."""

    def __init__(self, output_dir: str = './reports'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _safe_ts(self, ts: str) -> str:
        """Truncate ISO timestamp for display."""
        return ts[:19] if ts else 'N/A'

    # ── Markdown ────────────────────────────────────────────────────────

    def generate_markdown(self, diagnosis: dict) -> str:
        """Generate a Markdown report. Returns file path."""
        snapshot = diagnosis['snapshot']
        md = self._build_markdown(diagnosis, snapshot)
        path = self._write_file(md, snapshot, '.md')
        return path

    def _build_markdown(self, diagnosis: dict, snapshot) -> str:
        lines = []
        ns = snapshot.namespace
        ctx = snapshot.context or 'default'
        ts = self._safe_ts(snapshot.timestamp)

        lines.extend([
            f"# LogSentinel Namespace Diagnosis",
            f"",
            f"**Namespace:** `{ns}` | **Context:** `{ctx}` | **Time:** {ts}",
            f"",
        ])

        # Pod summary
        pod_summary = diagnosis.get('pod_summary', {})
        lines.extend([
            f"---",
            f"## Pods",
            f"",
            f"| Count | Healthy | Warning | Critical |",
            f"|-------|---------|---------|----------|",
            f"| {pod_summary.get('total', 0)} | {pod_summary.get('healthy', 0)} | {pod_summary.get('warning', 0)} | {pod_summary.get('unhealthy', 0)} |",
            f"",
        ])

        if snapshot.pods:
            lines.append("| Pod | Phase | Ready | Restarts | Age | Health |")
            lines.append("|-----|-------|-------|----------|-----|--------|")
            for p in snapshot.pods:
                lines.append(f"| {p.name} | {p.phase} | {p.ready} | {p.restarts} | {p.age} | {p.health} |")
                for c in p.containers:
                    if c.state != 'running' or c.reason:
                        lines.append(f"|  └─ {c.name} | {c.state} | {c.reason} | {c.restart_count} | | {c.image} |")
            lines.append("")

        # Resources
        if snapshot.resources:
            lines.extend([
                f"---",
                f"## Resources",
                f"",
                f"| Pod | CPU Usage | CPU Limit | MEM Usage | MEM Limit |",
                f"|-----|-----------|-----------|-----------|-----------|",
            ])
            for r in snapshot.resources:
                lines.append(f"| {r.pod} | {r.cpu_usage} | {r.cpu_limit} | {r.mem_usage} | {r.mem_limit} |")
            lines.append("")
        else:
            lines.extend([f"---", f"## Resources", f"", f"_Metrics server not available — resource usage unknown._", f""])

        # Events
        if snapshot.events:
            warnings = [e for e in snapshot.events if e.type == 'Warning']
            lines.extend([
                f"---",
                f"## Events ({len(warnings)} warnings, {len(snapshot.events) - len(warnings)} normal)",
                f"",
                "| Type | Timestamp | Reason | Message |",
                "|------|-----------|--------|---------|",
            ])
            displayed = warnings if warnings else snapshot.events[-15:]
            for e in displayed[-15:]:
                ts_short = self._safe_ts(e.timestamp)
                lines.append(f"| {e.type} | {ts_short} | {e.reason} | {e.message[:150]} |")
            lines.append("")

        # Workloads
        for label, wls in [('Deployments', snapshot.deployments), ('StatefulSets', snapshot.statefulsets), ('DaemonSets', snapshot.daemonsets)]:
            if wls:
                lines.extend([
                    f"---",
                    f"## {label}",
                    f"",
                    "| Name | Ready | Available | Desired | Status |",
                    "|------|-------|-----------|---------|--------|",
                ])
                for w in wls:
                    status = 'OK' if w.available >= w.desired else 'DEGRADED'
                    lines.append(f"| {w.name} | {w.ready} | {w.available} | {w.desired} | {status} |")
                lines.append("")

        # Services
        if snapshot.services:
            lines.extend([
                f"---",
                f"## Services",
                f"",
                "| Name | Type | Cluster IP | Ports |",
                "|------|------|------------|-------|",
            ])
            for s in snapshot.services:
                lines.append(f"| {s['name']} | {s['type']} | {s['cluster_ip']} | {s['ports']} |")
            lines.append("")

        # PVCs
        if snapshot.pvcs:
            lines.extend(["---", "## PVCs", "", "| Name | Status | Volume | Capacity |", "|------|--------|--------|----------|"])
            for p in snapshot.pvcs:
                lines.append(f"| {p['name']} | {p['status']} | {p['volume']} | {p['capacity']} |")
            lines.append("")

        # Issues
        if diagnosis.get('issues'):
            lines.extend(["---", "## Issues Found", ""])
            for i in diagnosis['issues']:
                lines.append(f"- **[{i.severity.upper()}]** [{i.category}] `{i.source}` — {i.message}")
            lines.append("")

        # Recommendations
        if diagnosis.get('recommendations'):
            lines.extend(["---", "## Recommendations", ""])
            for r in diagnosis['recommendations']:
                lines.append(f"- {r}")
            lines.append("")

        # Log analysis
        log_summary = diagnosis.get('log_summary', {})
        if log_summary and log_summary.get('total', 0) > 0:
            lines.extend([
                f"---",
                f"## Log Analysis",
                f"",
                f"Total entries: {log_summary.get('total', 0)} | Errors: {log_summary.get('errors', 0) or log_summary.get('error', 0)} | Warnings: {log_summary.get('warnings', 0) or log_summary.get('warning', 0)}",
                f"",
            ])

        # LLM
        if diagnosis.get('llm_insights'):
            lines.extend(["---", "## LLM Root Cause Analysis", "", diagnosis['llm_insights'], ""])

        # Collection errors
        if snapshot.errors:
            lines.extend(["---", "## Collection Warnings", ""])
            for e in snapshot.errors:
                lines.append(f"- ⚠ {e}")
            lines.append("")

        return '\n'.join(lines)

    # ── HTML ────────────────────────────────────────────────────────────

    def generate_html(self, diagnosis: dict) -> str:
        """Generate an HTML report. Returns file path."""
        snapshot = diagnosis['snapshot']
        html_content = self._build_html(diagnosis, snapshot)
        path = self._write_file(html_content, snapshot, '.html')
        return path

    def _build_html(self, diagnosis: dict, snapshot) -> str:
        ns = snapshot.namespace
        ctx = snapshot.context or 'default'
        ts = self._safe_ts(snapshot.timestamp)
        pod_summary = diagnosis.get('pod_summary', {})

        parts = [f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LogSentinel Diagnosis — {ns}</title>
<style>
:root {{ --red:#dc2626; --amber:#d97706; --green:#16a34a; --blue:#2563eb;
  --gray:#6b7280; --bg:#0f172a; --card:#1e293b; --border:#334155; --text:#e2e8f0;
  --text-muted:#94a3b8; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:system-ui,-apple-system,sans-serif; background:var(--bg);
  color:var(--text); padding:2rem; line-height:1.6; }}
h1 {{ font-size:1.75rem; color:#f8fafc; margin-bottom:.25rem; }}
h2 {{ font-size:1.25rem; color:#cbd5e1; margin:1.5rem 0 .75rem; padding-bottom:.5rem;
  border-bottom:1px solid var(--border); }}
.meta {{ color:var(--text-muted); font-size:.875rem; margin-bottom:1.5rem; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:8px;
  padding:1rem; margin-bottom:1rem; overflow-x:auto; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:.75rem; margin-bottom:1rem; }}
.stat {{ background:var(--card); border:1px solid var(--border); border-radius:8px;
  padding:1rem; text-align:center; }}
.stat-value {{ font-size:2rem; font-weight:700; }}
.stat-label {{ font-size:.75rem; color:var(--text-muted); text-transform:uppercase;
  letter-spacing:.05em; }}
table {{ width:100%; border-collapse:collapse; font-size:.875rem; }}
th {{ text-align:left; color:var(--text-muted); font-weight:600; padding:.5rem .75rem;
  border-bottom:2px solid var(--border); white-space:nowrap; }}
td {{ padding:.4rem .75rem; border-bottom:1px solid var(--border); }}
tr:hover {{ background:rgba(255,255,255,.03); }}
.badge {{ display:inline-block; padding:.15rem .5rem; border-radius:12px;
  font-size:.75rem; font-weight:600; text-transform:uppercase; }}
.badge-healthy {{ background:#14532d; color:#86efac; }}
.badge-warning {{ background:#451a03; color:#fcd34d; }}
.badge-critical {{ background:#450a0a; color:#fca5a5; }}
.badge-ok {{ background:#14532d; color:#86efac; }}
.badge-degraded {{ background:#450a0a; color:#fca5a5; }}
.issue {{ display:flex; gap:.75rem; padding:.5rem 0; border-bottom:1px solid var(--border); }}
.issue-sev {{ font-weight:700; min-width:70px; font-size:.8rem; text-transform:uppercase; }}
.issue-sev.critical {{ color:var(--red); }}
.issue-sev.warning {{ color:var(--amber); }}
.issue-sev.info {{ color:var(--blue); }}
.issue-body {{ flex:1; }}
.issue-cat {{ color:var(--text-muted); font-size:.75rem; }}
.issue-src {{ font-family:monospace; color:var(--text-muted); font-size:.8rem; }}
.recommendation {{ padding:.25rem 0 .25rem 1rem; border-left:3px solid var(--blue);
  margin:.25rem 0; }}
.llm-box {{ background:var(--card); border:1px solid var(--blue);
  border-radius:8px; padding:1rem; margin-top:1rem; white-space:pre-wrap;
  font-size:.9rem; }}
.muted {{ color:var(--text-muted); font-style:italic; }}
footer {{ margin-top:2rem; text-align:center; color:var(--text-muted);
  font-size:.75rem; border-top:1px solid var(--border); padding-top:1rem; }}
</style>
</head>
<body>
<h1>LogSentinel Namespace Diagnosis</h1>
<div class="meta">
  Namespace: <strong>{ns}</strong> &middot; Context: <strong>{ctx}</strong> &middot; Time: <strong>{ts}</strong>
</div>
''']

        # Summary stats
        parts.append('<div class="grid">')
        parts.append(f'<div class="stat"><div class="stat-value" style="color:var(--text)">{pod_summary.get("total", 0)}</div><div class="stat-label">Total Pods</div></div>')
        parts.append(f'<div class="stat"><div class="stat-value" style="color:var(--green)">{pod_summary.get("healthy", 0)}</div><div class="stat-label">Healthy</div></div>')
        parts.append(f'<div class="stat"><div class="stat-value" style="color:var(--amber)">{pod_summary.get("warning", 0)}</div><div class="stat-label">Warning</div></div>')
        parts.append(f'<div class="stat"><div class="stat-value" style="color:var(--red)">{pod_summary.get("unhealthy", 0)}</div><div class="stat-label">Critical</div></div>')
        warning_count = len([e for e in snapshot.events if e.type == 'Warning'])
        parts.append(f'<div class="stat"><div class="stat-value" style="color:var(--amber)">{warning_count}</div><div class="stat-label">Warning Events</div></div>')
        log_summary = diagnosis.get('log_summary', {})
        log_errs = log_summary.get('errors', log_summary.get('error', 0)) if log_summary else 0
        parts.append(f'<div class="stat"><div class="stat-value" style="color:var(--red)">{log_errs}</div><div class="stat-label">Log Errors</div></div>')
        parts.append('</div>')

        # Pods
        if snapshot.pods:
            parts.append('<h2>Pods</h2><div class="card"><table>')
            parts.append('<tr><th>Pod</th><th>Phase</th><th>Ready</th><th>Restarts</th><th>Age</th><th>Health</th><th>Containers</th></tr>')
            for p in snapshot.pods:
                badge = f'<span class="badge badge-{p.health}">{p.health}</span>'
                container_details = '<br>'.join(
                    f'<span style="font-size:.75rem">{c.name}: {c.state}, {c.reason or "—"}</span>'
                    for c in p.containers if c.state != 'running' or c.reason
                )
                parts.append(f'<tr><td style="font-family:monospace">{p.name}</td><td>{p.phase}</td><td>{p.ready}</td><td>{p.restarts}</td><td>{p.age}</td><td>{badge}</td><td>{container_details or "—"}</td></tr>')
            parts.append('</table></div>')

        # Resources
        if snapshot.resources:
            parts.append('<h2>Resources</h2><div class="card"><table>')
            parts.append('<tr><th>Pod</th><th>CPU Usage</th><th>CPU Limit</th><th>MEM Usage</th><th>MEM Limit</th></tr>')
            for r in snapshot.resources:
                parts.append(f'<tr><td style="font-family:monospace">{r.pod}</td><td>{r.cpu_usage}</td><td>{r.cpu_limit}</td><td>{r.mem_usage}</td><td>{r.mem_limit}</td></tr>')
            parts.append('</table></div>')
        else:
            parts.append('<h2>Resources</h2><p class="muted">Metrics server not available — resource usage unknown.</p>')

        # Events
        if snapshot.events:
            parts.append('<h2>Events</h2><div class="card"><table>')
            parts.append('<tr><th>Type</th><th>Time</th><th>Reason</th><th>Message</th></tr>')
            warnings = [e for e in snapshot.events if e.type == 'Warning']
            displayed = warnings if warnings else snapshot.events[-15:]
            for e in displayed[-15:]:
                color = 'var(--red)' if e.type == 'Warning' else ''
                parts.append(f'<tr><td style="color:{color};font-weight:600">{e.type}</td><td style="white-space:nowrap">{self._safe_ts(e.timestamp)}</td><td>{e.reason}</td><td style="max-width:400px">{_html.escape(e.message[:200])}</td></tr>')
            parts.append('</table></div>')

        # Workloads
        for label, wls in [('Deployments', snapshot.deployments), ('StatefulSets', snapshot.statefulsets), ('DaemonSets', snapshot.daemonsets)]:
            if wls:
                parts.append(f'<h2>{label}</h2><div class="card"><table>')
                parts.append('<tr><th>Name</th><th>Ready</th><th>Available</th><th>Desired</th><th>Status</th></tr>')
                for w in wls:
                    ok = w.available >= w.desired
                    badge = f'<span class="badge badge-{"ok" if ok else "degraded"}">{"OK" if ok else "DEGRADED"}</span>'
                    parts.append(f'<tr><td style="font-family:monospace">{w.name}</td><td>{w.ready}</td><td>{w.available}</td><td>{w.desired}</td><td>{badge}</td></tr>')
                parts.append('</table></div>')

        # Services
        if snapshot.services:
            parts.append('<h2>Services</h2><div class="card"><table>')
            parts.append('<tr><th>Name</th><th>Type</th><th>Cluster IP</th><th>Ports</th></tr>')
            for s in snapshot.services:
                parts.append(f'<tr><td style="font-family:monospace">{s["name"]}</td><td>{s["type"]}</td><td>{s["cluster_ip"]}</td><td>{s["ports"]}</td></tr>')
            parts.append('</table></div>')

        # PVCs
        if snapshot.pvcs:
            parts.append('<h2>PVCs</h2><div class="card"><table>')
            parts.append('<tr><th>Name</th><th>Status</th><th>Volume</th><th>Capacity</th></tr>')
            for p in snapshot.pvcs:
                parts.append(f'<tr><td style="font-family:monospace">{p["name"]}</td><td>{p["status"]}</td><td style="font-family:monospace;font-size:.8rem">{p["volume"]}</td><td>{p["capacity"]}</td></tr>')
            parts.append('</table></div>')

        # Issues
        if diagnosis.get('issues'):
            parts.append('<h2>Issues Found</h2>')
            for i in diagnosis['issues']:
                parts.append(f'''<div class="card issue">
<div class="issue-sev {i.severity}">{i.severity}</div>
<div class="issue-body">
<div style="font-weight:600">{_html.escape(i.message)}</div>
<div class="issue-src">{i.source}</div>
<div class="issue-cat">{i.category}</div>
</div></div>''')

        # Recommendations
        if diagnosis.get('recommendations'):
            parts.append('<h2>Recommendations</h2><div class="card">')
            for r in diagnosis['recommendations']:
                parts.append(f'<div class="recommendation">{_html.escape(r)}</div>')
            parts.append('</div>')

        # Log analysis
        if log_summary and log_summary.get('total', 0) > 0:
            parts.append(f'<h2>Log Analysis</h2><p class="muted">Total entries: {log_summary.get("total", 0)} | Errors: {log_summary.get("errors", 0) or log_summary.get("error", 0)} | Warnings: {log_summary.get("warnings", 0) or log_summary.get("warning", 0)}</p>')

        # LLM
        if diagnosis.get('llm_insights'):
            parts.append(f'<h2>LLM Root Cause Analysis</h2><div class="llm-box">{_html.escape(str(diagnosis["llm_insights"]))}</div>')

        # Collection errors
        if snapshot.errors:
            parts.append('<h2>Collection Warnings</h2><div class="card">')
            for e in snapshot.errors:
                parts.append(f'<p class="muted">⚠ {e}</p>')
            parts.append('</div>')

        parts.append(f'<footer>Generated by LogSentinel on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</footer>')
        parts.append('</body></html>')
        return '\n'.join(parts)

    # ── PDF (via existing pattern) ──────────────────────────────────────

    def generate_pdf(self, diagnosis: dict) -> str:
        """Generate a PDF report. Falls back to HTML on failure. Returns file path."""
        snapshot = diagnosis['snapshot']
        md = self._build_markdown(diagnosis, snapshot)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_ns = snapshot.namespace.replace(' ', '_').lower()
        html_path = None

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

            pdf_path = os.path.join(self.output_dir, f"diagnose_{safe_ns}_{timestamp}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                    leftMargin=36, rightMargin=36,
                                    topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle('DiagnoseTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=12)
            h2_style = ParagraphStyle('DiagnoseH2', parent=styles['Heading2'], fontSize=14, spaceAfter=6, spaceBefore=12)
            body_style = ParagraphStyle('DiagnoseBody', parent=styles['Normal'], fontSize=9, leading=12)
            mono_style = ParagraphStyle('DiagnoseMono', parent=styles['Normal'], fontSize=8, leading=10, fontName='Courier')

            story = []
            for line in md.split('\n'):
                if not line.strip():
                    story.append(Spacer(1, 4))
                elif line.startswith('# '):
                    story.append(Paragraph(_html.escape(line[2:]), title_style))
                elif line.startswith('## '):
                    story.append(Paragraph(_html.escape(line[3:]), h2_style))
                elif line.startswith('|'):
                    story.append(Paragraph(_html.escape(line), mono_style))
                else:
                    story.append(Paragraph(_html.escape(line), body_style))

            doc.build(story)
            return pdf_path
        except ImportError:
            # Fallback to HTML
            if html_path is None:
                html_path = self.generate_html(diagnosis)
            return html_path
        except Exception:
            if html_path is None:
                html_path = self.generate_html(diagnosis)
            return html_path

    # ── Helpers ─────────────────────────────────────────────────────────

    def _write_file(self, content: str, snapshot, extension: str) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_ns = snapshot.namespace.replace(' ', '_').lower()
        filename = f"diagnose_{safe_ns}_{timestamp}{extension}"
        path = os.path.join(self.output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path
