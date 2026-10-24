# -*- coding: utf-8 -*-
"""arXiv 论文日报：抓取 AI 与医疗 AI 方向最新论文，生成每日卡片笔记。

修改下面两个常量即可调整关注方向。
"""
import sys, os, re, urllib.parse, xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http_get, today, clean, write_note  # noqa: E402

API = "http://export.arxiv.org/api/query"

# 通用 AI 方向
AI_QUERY = "cat:cs.AI OR cat:cs.LG OR cat:cs.CV OR cat:cs.CL"
# 医疗 / 生物 AI 方向
MED_QUERY = "(cat:cs.AI OR cat:cs.LG OR cat:cs.CV) AND (abs:medical OR abs:clinical OR abs:radiology OR abs:pathology)"
# 关键词高亮（命中则优先展示）
KEYWORDS = ["llm", "agent", "multimodal", "reasoning", "medical", "clinical",
            "radiology", "diffusion", "rlhf", "evaluation"]

MAX_PER_QUERY = 15
NS = {"a": "http://www.w3.org/2005/Atom"}


def fetch(query, max_results=MAX_PER_QUERY):
    url = (f"{API}?search_query={urllib.parse.quote(query)}&sortBy=submittedDate"
           f"&sortOrder=descending&max_results={max_results}")
    xml = http_get(url, timeout=40)
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", NS):
        eid = (e.findtext("a:id", "", NS) or "").strip()
        title = clean(e.findtext("a:title", "", NS))
        summary = clean(e.findtext("a:summary", "", NS))
        published = (e.findtext("a:published", "", NS) or "")[:10]
        authors = [a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)]
        cats = [c.get("term") for c in e.findall("a:category", NS) if c.get("term")]
        pdf = ""
        for link in e.findall("a:link", NS):
            if link.get("title") == "pdf":
                pdf = link.get("href")
        out.append({
            "id": eid, "title": title, "summary": summary, "published": published,
            "authors": authors, "cats": cats, "pdf": pdf or eid,
        })
    return out


def score(p):
    s = 0
    blob = (p["title"] + " " + p["summary"]).lower()
    for k in KEYWORDS:
        if k in blob:
            s += 1
    return s


def render(papers, heading):
    lines = [heading]
    if not papers:
        lines.append("\n_本次未抓到内容（源站可能临时不可用）。_\n")
        return lines
    lines.append("\n| 论文 | 方向 | 提交 | 一句话摘要 |")
    lines.append("|---|---|---|---|")
    for p in papers:
        url = p["id"]
        link = f"[{clean(p['title'], 80)}]({url})"
        cats = ", ".join(p["cats"][:2])
        lines.append(f"| {link} | {cats} | {p['published']} | {clean(p['summary'], 150)} |")
    lines.append("")
    # 命中关键词的论文单独列出要点
    hot = [p for p in papers if score(p) > 0]
    if hot:
        lines.append("### 命中关键词的高相关论文\n")
        for p in hot[:8]:
            lines.append(f"- **[{clean(p['title'], 100)}]({p['id']})**")
            lines.append(f"  - 作者：{clean('、'.join(p['authors'][:3]) + ('等' if len(p['authors']) > 3 else ''), 90)}")
            lines.append(f"  - 要点：{clean(p['summary'], 280)}")
            lines.append(f"  - PDF：{p['pdf']}\n")
    return lines


def main():
    date = today()
    lines = []
    try:
        ai = sorted(fetch(AI_QUERY), key=score, reverse=True)
        lines += render(ai, "## AI 方向最新论文\n")
    except Exception as e:
        lines += ["## AI 方向最新论文\n", f"\n_抓取失败：{e}_\n"]
    try:
        med = sorted(fetch(MED_QUERY), key=score, reverse=True)
        lines += render(med, "## 医疗 / 临床 AI 方向\n")
    except Exception as e:
        lines += ["## 医疗 / 临床 AI 方向\n", f"\n_抓取失败：{e}_\n"]

    lines.append("---\n")
    lines.append("数据来源：[arXiv API](http://export.arxiv.org/api/query) · "
                 "相关主线：[[人工智能/index|人工智能]] · [[医疗/index|医疗]]")
    write_note(f"daily/arxiv/{date}.md", f"arXiv 日报 {date}",
               ["情报", "论文", "AI"], lines,
               description="每日 AI 与医疗 AI 最新论文汇总")


if __name__ == "__main__":
    main()
