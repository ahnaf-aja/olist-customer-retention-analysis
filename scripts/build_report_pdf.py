"""
Konversi reports/business_analysis_report.md -> reports/business_analysis_report.pdf
Cara kerja: Markdown -> HTML (dengan CSS laporan) -> Microsoft Edge headless --print-to-pdf.

    python scripts/build_report_pdf.py
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys

import markdown

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "reports" / "business_analysis_report.md"
HTML = ROOT / "reports" / "business_analysis_report.html"
PDF = ROOT / "reports" / "business_analysis_report.pdf"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    shutil.which("msedge") or "", shutil.which("chrome") or "", shutil.which("chromium") or "",
]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; line-height: 1.5; color: #1d1d1b; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always;
         border-left: 6px solid #2a78d6; padding-left: 14mm; }
.cover .kicker { color: #2a78d6; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; font-size: 10pt; }
.cover h1 { font-size: 28pt; line-height: 1.15; margin: 6mm 0 4mm; border: 0; }
.cover .sub { font-size: 12pt; color: #52514e; max-width: 140mm; }
.cover .meta { margin-top: 18mm; font-size: 9.5pt; color: #52514e; }
.cover .meta b { color: #1d1d1b; }
h1 { display: none; }               /* judul markdown diganti cover */
h2 { font-size: 15pt; color: #0b0b0b; border-bottom: 2px solid #2a78d6; padding-bottom: 2mm; margin: 9mm 0 3mm;
     page-break-after: avoid; }
h3 { font-size: 11.5pt; color: #1f5aa6; margin: 6mm 0 2mm; page-break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 6mm; }
table { width: 100%; border-collapse: collapse; margin: 3mm 0 5mm; font-size: 8.8pt; page-break-inside: avoid; }
th { background: #2a78d6; color: #fff; text-align: left; padding: 2mm 2.5mm; font-weight: 600; }
td { padding: 1.6mm 2.5mm; border-bottom: 1px solid #e3e2dd; vertical-align: top; }
tr:nth-child(even) td { background: #f6f8fb; }
img { display: block; max-width: 100%; max-height: 95mm; margin: 3mm auto 5mm; page-break-inside: avoid; }
code { font-family: Consolas, monospace; font-size: 8.8pt; background: #f1f0ec; padding: 0 1mm; border-radius: 2px; }
blockquote { margin: 3mm 0; padding: 2mm 4mm; border-left: 3px solid #eb6834; background: #fdf3ee; color: #3a3936; }
hr { border: 0; border-top: 1px solid #e3e2dd; margin: 5mm 0; }
strong { color: #0b0b0b; }
.toc { page-break-after: always; }
.toc h2 { margin-top: 0; }
.toc ul { list-style: none; padding-left: 0; font-size: 10.5pt; line-height: 1.9; }
p:has(+ table), p:has(+ p > img) { break-after: avoid; page-break-after: avoid; }
.finding { page-break-inside: avoid; }
"""


def build_html() -> str:
    text = MD.read_text(encoding="utf-8")
    # Ambil judul & blok meta (sebelum '---' pertama) untuk halaman cover
    head, body = text.split("\n---\n", 1)
    title = re.search(r"^# (.+)$", head, re.M).group(1)
    meta_lines = [l.strip() for l in head.splitlines()[1:] if l.strip()]
    meta_html = "<br>".join(markdown.markdown(l)[3:-4] for l in meta_lines)

    # Gambar: path relatif '../visuals/x.png' -> URI file absolut agar Edge dapat memuatnya
    body = re.sub(r"\]\(\.\./visuals/([^)]+)\)",
                  lambda m: "](" + (ROOT / "visuals" / m.group(1)).as_uri() + ")", body)
    html_body = markdown.markdown(body, extensions=["tables", "sane_lists"])

    # Daftar isi dari heading level 2
    heads = re.findall(r"<h2>(.+?)</h2>", html_body)
    toc = "<section class='toc'><h2>Daftar Isi</h2><ul>" + "".join(
        f"<li>{h}</li>" for h in heads) + "</ul></section>"

    cover = f"""
    <section class="cover">
      <div class="kicker">Laporan Analisis Bisnis</div>
      <h1 style="display:block">{title}</h1>
      <div class="sub">Analisis sebaran geografis, konsentrasi pasar, dan loyalitas pelanggan
        marketplace e-commerce Brasil, disertai rekomendasi bisnis dan rancangan dashboard Power BI.</div>
      <div class="meta">{meta_html}</div>
    </section>"""
    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head><body>{cover}{toc}{html_body}</body></html>"""


def main() -> None:
    HTML.write_text(build_html(), encoding="utf-8")
    browser = next((p for p in EDGE_CANDIDATES if p and Path(p).exists()), None)
    if not browser:
        sys.exit("Edge/Chrome tidak ditemukan. Buka file HTML di browser lalu Print -> Save as PDF.")
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--allow-file-access-from-files", f"--print-to-pdf={PDF}", HTML.as_uri()],
                   check=True, timeout=120)
    print("PDF dibuat:", PDF, f"({PDF.stat().st_size/1024:,.0f} KB)")


if __name__ == "__main__":
    main()
