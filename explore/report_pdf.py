"""
Turn a report in Markdown (report/*.md) into a PDF in the Rose Pine Dawn theme of the plots.

Markdown -> HTML with the `markdown` package (tables), $...$ and $$...$$ formulas -> MathML
with `latex2mathml` (no network needed), then printed to PDF by headless Microsoft Edge.
Images are linked relative to the Markdown file, so the HTML is written next to it and removed
afterwards.

Inputs: a Markdown file. Output: the PDF next to it (same name, .pdf).
Usage: python explore/report_pdf.py report/REPORT_semplice.md
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import markdown
from latex2mathml.converter import convert

sys.path.insert(0, "explore")
from report_style import BASE, OVERLAY, HL_MED, SUBTLE, TEXT, PINE, IRIS  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = f"""
@page {{ size: A4; margin: 16mm 15mm; background: {BASE}; }}
html, body {{ background: {BASE}; }}
body {{ color: {TEXT}; font-family: "Segoe UI", Calibri, sans-serif; font-size: 10.5pt;
       line-height: 1.5; margin: 0; }}
h1 {{ color: {PINE}; font-size: 20pt; margin: 0 0 4pt; }}
h2 {{ color: {PINE}; font-size: 14.5pt; margin: 18pt 0 6pt; break-after: avoid; }}
h3 {{ color: {IRIS}; font-size: 12pt; margin: 14pt 0 4pt; break-after: avoid; }}
p, li {{ margin: 4pt 0; }}
em {{ color: {SUBTLE}; }}
hr {{ border: none; border-top: 1px solid {HL_MED}; margin: 12pt 0; }}
img {{ display: block; max-width: 100%; max-height: 105mm; margin: 8pt auto; break-inside: avoid; }}
table {{ border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; break-inside: avoid; }}
th, td {{ border-bottom: 1px solid {HL_MED}; padding: 3pt 8pt; text-align: left; }}
th {{ background: {OVERLAY}; }}
math[display="block"] {{ margin: 8pt 0; font-size: 11.5pt; }}
a {{ color: {PINE}; }}
"""


def formulas(text):
    """Replace $$...$$ and $...$ with MathML before Markdown sees them (it would mangle _ and *)."""
    keep = []

    def put(tex, block):
        keep.append(convert(tex.strip(), display="block" if block else "inline"))
        return f"\x00{len(keep) - 1}\x00"

    text = re.sub(r"\$\$(.+?)\$\$", lambda m: put(m.group(1), True), text, flags=re.S)
    # inline: an opening $ followed by a digit or a space is a dollar amount ($1, $100), not math
    text = re.sub(r"(?<![\\$])\$(?![\d ])([^$\n]+?)\$", lambda m: put(m.group(1), False), text)
    return text, keep


def main(md_path):
    md_path = os.path.abspath(md_path)
    text, keep = formulas(open(md_path, encoding="utf-8").read())
    # GitHub starts a list right after a line of text; Python-Markdown needs a blank line first
    text = re.sub(r"(?m)^(?![-*] |\d+\. |\s)(.+)\n(?=(?:[-*] |\d+\. ))", r"\1\n\n", text)
    body = markdown.markdown(text, extensions=["tables"])
    body = re.sub("\x00(\\d+)\x00", lambda m: keep[int(m.group(1))], body)
    title = re.search(r"<h1>(.*?)</h1>", body).group(1)
    html = (f'<!doctype html><html lang="it"><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    base = os.path.splitext(md_path)[0]
    tmp, pdf = base + "_tmp.html", base + ".pdf"
    if os.path.exists(pdf):
        os.remove(pdf)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    profile = tempfile.mkdtemp()      # own profile, so a running Edge does not take over the job
    try:
        subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                        f"--print-to-pdf={pdf}", "file:///" + tmp.replace(os.sep, "/")],
                       check=True, capture_output=True, timeout=120)
        # msedge.exe hands the job to a child process and returns at once: wait for the file
        for _ in range(120):
            if os.path.exists(pdf) and os.path.getsize(pdf) > 0:
                size = os.path.getsize(pdf)
                time.sleep(2)
                if os.path.getsize(pdf) == size:
                    break
            time.sleep(1)
        else:
            raise RuntimeError("Edge wrote no PDF")
    finally:
        os.remove(tmp)
        shutil.rmtree(profile, ignore_errors=True)
    print(pdf)


if __name__ == "__main__":
    main(sys.argv[1])
