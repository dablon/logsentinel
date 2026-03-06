"""
PDF/HTML/Markdown report generator for log analysis results.
"""
import html
import os
from datetime import datetime
from typing import Dict


class PDFGenerator:
    """Generate reports (Markdown, HTML, PDF) from log analysis results."""

    def __init__(self, output_dir: str = '/tmp/logsentinel_reports'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _create_markdown(self, analysis: Dict, title: str = "Log Analysis") -> str:
        """Return a Markdown string summarising the analysis."""
        summary = analysis.get('summary', {})
        errors = analysis.get('errors', [])
        warnings = analysis.get('warnings', [])
        recommendations = analysis.get('analysis', {}).get('recommendations', [])

        lines = [
            f"# {title} Report",
            f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n",
            "## Summary",
            f"| Metric | Count |",
            f"|--------|-------|",
            f"| Total  | {summary.get('total', 0)} |",
            f"| Errors | {summary.get('error', 0)} |",
            f"| Warnings | {summary.get('warning', 0)} |",
            f"| Info | {summary.get('info', 0)} |",
        ]

        if errors:
            lines += ["\n## Top Errors"]
            for e in errors[:10]:
                lines.append(f"- `[{e.get('level', 'ERROR')}]` {e.get('message', '')[:120]}")

        if warnings:
            lines += ["\n## Top Warnings"]
            for w in warnings[:10]:
                lines.append(f"- {w.get('message', '')[:120]}")

        if recommendations:
            lines += ["\n## Recommendations"]
            for rec in recommendations:
                lines.append(f"- {rec}")

        if analysis.get('llm_insights'):
            lines += ["\n## AI Insights", analysis['llm_insights']]

        return '\n'.join(lines)

    def generate(self, analysis: Dict, title: str = "Log Analysis") -> str:
        """Write a Markdown report and return the file path.

        If the *reportlab* library is installed, a PDF is also produced and
        its path is returned instead.  Falls back to Markdown when reportlab
        is unavailable so that the method always succeeds.
        """
        md_content = self._create_markdown(analysis, title)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_title = title.replace(' ', '_').lower()

        md_path = os.path.join(self.output_dir, f"{safe_title}_{timestamp}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet

            pdf_path = os.path.join(self.output_dir, f"{safe_title}_{timestamp}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=letter)
            styles = getSampleStyleSheet()
            story = [Paragraph(html.escape(line).replace('\n', '<br/>'), styles['Normal'])
                     for line in md_content.split('\n') if line.strip()]
            doc.build(story)
            return pdf_path
        except ImportError:
            return md_path

    def generate_html(self, analysis: Dict, title: str = "Log Analysis") -> str:
        """Write an HTML report and return the file path."""
        md_content = self._create_markdown(analysis, title)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_title = title.replace(' ', '_').lower()

        # Simple Markdown→HTML conversion (no external deps required)
        html_lines = ['<!DOCTYPE html><html><head>',
                      f'<meta charset="utf-8"><title>{title}</title>',
                      '<style>body{font-family:sans-serif;max-width:900px;margin:auto;padding:1rem}'
                      'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.3rem .6rem}</style>',
                      '</head><body>']
        for line in md_content.split('\n'):
            if line.startswith('# '):
                html_lines.append(f'<h1>{line[2:]}</h1>')
            elif line.startswith('## '):
                html_lines.append(f'<h2>{line[3:]}</h2>')
            elif line.startswith('- '):
                html_lines.append(f'<li>{html.escape(line[2:])}</li>')
            elif line.startswith('|'):
                html_lines.append(f'<tr>{"".join(f"<td>{html.escape(c.strip())}</td>" for c in line.strip("|").split("|"))}</tr>')
            elif line.strip():
                html_lines.append(f'<p>{line}</p>')
        html_lines.append('</body></html>')

        html_path = os.path.join(self.output_dir, f"{safe_title}_{timestamp}.html")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_lines))
        return html_path
