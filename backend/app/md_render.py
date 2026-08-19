# -*- coding: utf-8 -*-
"""轻量 Markdown -> HTML 渲染（服务端，用于报告新页面查看）。

支持：标题 / 表格 / 无序·有序列表 / 引用 / 代码块 / 行内代码 / 粗体 / 斜体 / 分隔线。
所有文本先经过 html.escape 转义，防止 XSS 注入。
"""
import html
import re
from typing import Dict, List


def _inline(s: str) -> str:
    t = html.escape(s)
    t = re.sub(r"`([^`]+)`", lambda m: "<code>%s</code>" % m.group(1), t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
    return t


def render_markdown(src: str) -> str:
    lines = (src or "").split("\n")
    out: List[str] = []
    i = 0
    is_table = lambda l: bool(re.match(r"^\s*\|.*\|\s*$", l))
    while i < len(lines):
        line = lines[i]
        t = line.strip()
        if not t:
            i += 1
            continue

        # 代码块
        if t.startswith("```"):
            buf: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append('<pre class="rp-code"><code>%s</code></pre>' % html.escape("\n".join(buf)))
            continue

        # 表格
        if is_table(t):
            rows: List[str] = []
            while i < len(lines) and is_table(lines[i].strip()):
                rows.append(lines[i].strip())
                i += 1
            if len(rows) >= 2:
                cells = lambda r: [c.strip() for c in r.split("|")[1:-1]]
                header = cells(rows[0])
                body = [cells(r) for r in rows[2:]]
                th = "".join("<th>%s</th>" % _inline(h) for h in header)
                trs = "".join(
                    "<tr>%s</tr>" % "".join("<td>%s</td>" % _inline(c) for c in row)
                    for row in body
                )
                out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (th, trs))
            else:
                out.append("<p>%s</p>" % _inline(rows[0]))
                i -= len(rows) - 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", t)
        if m:
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, _inline(m.group(2)), level))
            i += 1
            continue

        # 分隔线
        if re.match(r"^(-{3,}|\*{3,})$", t):
            out.append("<hr/>")
            i += 1
            continue

        # 引用
        if re.match(r"^>\s?", t):
            buf: List[str] = []
            while i < len(lines) and re.match(r"^\s*>\s?", lines[i]):
                buf.append(_inline(re.sub(r"^\s*>\s?", "", lines[i])))
                i += 1
            out.append("<blockquote>%s</blockquote>" % "<br/>".join(buf))
            continue

        # 列表
        m_ul = re.match(r"^\s*[-*]\s+(.*)$", t)
        m_ol = re.match(r"^\s*\d+\.\s+(.*)$", t)
        if m_ul or m_ol:
            ordered = bool(m_ol)
            items: List[str] = []
            pat = re.compile(r"^\s*\d+\.\s+(.*)$") if ordered else re.compile(r"^\s*[-*]\s+(.*)$")
            while i < len(lines):
                mm = pat.match(lines[i])
                if not mm:
                    break
                items.append(_inline(mm.group(1)))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % it for it in items), tag))
            continue

        out.append("<p>%s</p>" % _inline(t))
        i += 1
    return "\n".join(out)


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title} · 碳减排分析报告</title>
<style>
:root {{ --accent: #0d6efd; --accent-d: #0a58ca; --border: #e0e0e0; --muted: #777; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f4f6f8; color: #222; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif; }}
.rp-topbar {{ position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 12px;
  padding: 10px 20px; background: #fff; border-bottom: 1px solid var(--border); }}
.rp-topbar .rp-brand {{ font-weight: 700; font-size: 14px; color: var(--accent-d); }}
.rp-topbar .rp-meta {{ flex: 1; font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.rp-topbar a, .rp-topbar button {{ font-size: 12px; padding: 6px 14px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border); background: #f6f8fa; color: #333; text-decoration: none; }}
.rp-topbar a:hover, .rp-topbar button:hover {{ border-color: var(--accent); color: var(--accent-d); }}
.rp-engine {{ font-size: 10px; padding: 3px 8px; border-radius: 10px; font-weight: 600; white-space: nowrap; }}
.rp-engine.llm {{ background: #e3f2fd; color: var(--accent-d); border: 1px solid var(--accent); }}
.rp-engine.template {{ background: #f0f0f0; color: var(--muted); border: 1px solid var(--border); }}
.rp-wrap {{ max-width: 860px; margin: 0 auto; padding: 28px 24px 60px; background: #fff; min-height: 100vh;
  box-shadow: 0 1px 6px rgba(0,0,0,.06); }}
.rp-content {{ line-height: 1.75; font-size: 14px; }}
.rp-content h1 {{ font-size: 22px; margin: 8px 0 16px; padding-bottom: 10px; border-bottom: 2px solid var(--accent); }}
.rp-content h2 {{ font-size: 17px; margin: 22px 0 10px; color: var(--accent-d); }}
.rp-content h3 {{ font-size: 15px; margin: 16px 0 8px; }}
.rp-content h4 {{ font-size: 13.5px; margin: 14px 0 6px; }}
.rp-content p {{ margin: 8px 0; }}
.rp-content table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
.rp-content th, .rp-content td {{ border: 1px solid var(--border); padding: 6px 10px; text-align: left; }}
.rp-content th {{ background: #f5f7fa; font-weight: 600; white-space: nowrap; }}
.rp-content tr:nth-child(even) td {{ background: rgba(127,127,127,.04); }}
.rp-content blockquote {{ margin: 10px 0; padding: 8px 14px; border-left: 3px solid var(--accent);
  background: rgba(13,110,253,.05); color: #555; border-radius: 0 6px 6px 0; }}
.rp-content code {{ background: #f0f0f0; padding: 1px 5px; border-radius: 4px; font-size: 12.5px;
  font-family: "SF Mono", Menlo, Consolas, monospace; }}
.rp-content pre.rp-code {{ background: #1e2530; color: #d8e0ea; padding: 14px; border-radius: 8px;
  overflow: auto; font-size: 12.5px; }}
.rp-content pre.rp-code code {{ background: transparent; color: inherit; padding: 0; }}
.rp-content ul, .rp-content ol {{ margin: 8px 0; padding-left: 24px; }}
.rp-content li {{ margin: 4px 0; }}
.rp-content hr {{ border: none; border-top: 1px solid var(--border); margin: 18px 0; }}
.rp-content strong {{ color: var(--accent-d); }}
.rp-foot {{ max-width: 860px; margin: 0 auto; padding: 0 24px 40px; color: #aaa; font-size: 11px; text-align: center; }}
@media print {{
  .rp-topbar {{ display: none; }}
  .rp-wrap {{ box-shadow: none; padding: 0; }}
  body {{ background: #fff; }}
}}
</style>
</head>
<body>
<div class="rp-topbar">
  <span class="rp-brand">碳减排数字孪生平台</span>
  <span class="rp-engine {engine}">{engine_label}</span>
  <span class="rp-meta">{meta}</span>
  <a href="/" target="_self">返回平台</a>
  <button onclick="window.print()">打印 / 另存 PDF</button>
</div>
<div class="rp-wrap"><div class="rp-content">{body}</div></div>
<div class="rp-foot">由碳减排数字孪生平台生成 · {generated_at}</div>
</body>
</html>
"""


def render_report_page(markdown: str, meta: Dict) -> str:
    """渲染报告为完整 HTML 页面（新页面查看）。meta 含 title/created_at/engine 等。"""
    engine = (meta.get("engine") or "template")
    engine_label = "AI 大模型生成" if engine == "llm" else "本地模板生成"
    meta_line = " · ".join(x for x in [
        meta.get("strategy_name") or "",
        meta.get("scenario") or "",
        meta.get("created_at") or "",
    ] if x)
    return _PAGE_TEMPLATE.format(
        title=html.escape(meta.get("title") or "碳减排分析报告"),
        engine=engine,
        engine_label=engine_label,
        meta=html.escape(meta_line),
        body=render_markdown(markdown),
        generated_at=html.escape(meta.get("created_at") or ""),
    )
