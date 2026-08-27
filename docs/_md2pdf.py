#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时脚本：Markdown -> HTML（保留格式），再由 weasyprint 命令行转 PDF。

用法：python3 _md2pdf.py <md文件...>
"""
import os
import sys
import markdown

CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 20mm;
  @bottom-center { content: counter(page); font-size: 9pt; color: #999; }
}
* { box-sizing: border-box; }
body {
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Songti SC", sans-serif;
  font-size: 10.5pt; line-height: 1.75; color: #222; margin: 0;
}
h1 { font-size: 19pt; color: #111; border-bottom: 2.5px solid #0d6efd; padding-bottom: 8px; margin: 6px 0 16px; }
h2 { font-size: 14.5pt; color: #0a58ca; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; margin: 22px 0 10px; }
h3 { font-size: 12.5pt; color: #1a1a1a; margin: 16px 0 8px; }
h4 { font-size: 11.5pt; color: #333; margin: 14px 0 6px; }
p { margin: 8px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.5pt; }
th, td { border: 1px solid #c9cdd3; padding: 5px 9px; text-align: left; vertical-align: top; }
th { background: #f0f4f8; font-weight: 600; white-space: nowrap; }
tr:nth-child(even) td { background: #fafbfc; }
blockquote {
  margin: 10px 0; padding: 8px 14px;
  border-left: 3.5px solid #0d6efd; background: #f2f6fd; color: #555;
}
blockquote p { margin: 4px 0; }
pre {
  background: #f6f8fa; border: 1px solid #dde1e6; border-radius: 5px;
  padding: 10px 12px; font-size: 9pt; line-height: 1.55;
  white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;
}
code {
  font-family: "SF Mono", Menlo, Consolas, "Courier New", monospace;
  font-size: 0.92em;
}
p code, li code, td code, th code { background: #eef0f2; padding: 1px 5px; border-radius: 3px; }
pre code { background: transparent; padding: 0; }
ul, ol { margin: 8px 0; padding-left: 24px; }
li { margin: 3px 0; }
hr { border: none; border-top: 1px solid #d0d3d8; margin: 18px 0; }
strong { color: #0a58ca; }
a { color: #0d6efd; text-decoration: none; }
"""


def convert(md_path: str, html_path: str) -> None:
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "toc", "nl2br"],
    )
    title = os.path.splitext(os.path.basename(md_path))[0]
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>"
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK  {md_path}  ->  {html_path}")


if __name__ == "__main__":
    files = sys.argv[1:]
    if not files:
        print("usage: python3 _md2pdf.py <md文件...>")
        sys.exit(1)
    for f in files:
        out = os.path.splitext(f)[0] + ".html"
        convert(f, out)
