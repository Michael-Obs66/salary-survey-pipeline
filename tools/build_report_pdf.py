"""Render README.md (with figures) to a PDF case study.  python tools/build_report_pdf.py"""
from pathlib import Path

import markdown
from weasyprint import HTML

ROOT = Path(__file__).resolve().parent.parent
CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm;
        @bottom-center { content: counter(page) " / " counter(pages); font-size: 8pt; color: #888; } }
body { font-family: 'Inter', 'DejaVu Sans', sans-serif; font-size: 9.3pt; line-height: 1.5; color: #0b0b0b; }
h1 { font-size: 19pt; line-height: 1.2; margin: 0 0 4pt 0; }
h2 { font-size: 13pt; margin: 18pt 0 6pt 0; padding-bottom: 3pt; border-bottom: 1.5px solid #2a78d6; page-break-after: avoid; }
p { margin: 5pt 0; } strong { font-weight: 650; }
blockquote { margin: 8pt 0; padding: 7pt 11pt; background: #f1f5fb; border-left: 3px solid #2a78d6; color: #1d2733; }
blockquote p { margin: 0; }
table { border-collapse: collapse; width: 100%; margin: 7pt 0; font-size: 8.4pt; page-break-inside: auto; }
th { background: #eef1f5; text-align: left; } th, td { border: 1px solid #d9dce1; padding: 3.5pt 6pt; vertical-align: top; }
tr { page-break-inside: avoid; }
img { max-width: 100%; display: block; margin: 8pt auto; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; background: #f3f2ef; padding: 0 2pt; }
pre { background: #f6f5f2; border: 1px solid #e4e3df; padding: 7pt 9pt; font-size: 7.6pt; line-height: 1.4;
      white-space: pre; overflow: hidden; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
ul { margin: 4pt 0 4pt 14pt; padding: 0; } li { margin: 2pt 0; }
hr { border: none; border-top: 1px solid #e4e3df; margin: 10pt 0; }
"""
md = (ROOT / "README.md").read_text()
html = markdown.markdown(md, extensions=["tables", "fenced_code"])
out = ROOT / "reports" / "Portfolio_1_Salary_Survey_Data_Pipeline.pdf"
HTML(string=f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html}</body></html>",
     base_url=str(ROOT)).write_pdf(out)
print(out)
