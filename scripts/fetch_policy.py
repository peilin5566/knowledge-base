# -*- coding: utf-8 -*-
"""医疗政策与指南追踪：PubMed 最新指南 + WHO 新闻 + 国家卫健委动态 + 自定义 RSS。

自定义源：在 workflow 的 env 里设置 POLICY_RSS（多个 RSS 用逗号分隔）。
"""
import sys, os, re, json, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http_get, http_json, today, clean, write_note  # noqa: E402

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# 指南检索式（可在下面直接改）
PUBMED_TERM = '("practice guideline"[Publication Type] OR "guideline"[Title]) AND ("2025"[PDAT] OR "2026"[PDAT])'
WHO_RSS = "https://www.who.int/rss-feeds/news-english.xml"
NHC_URLS = [
    ("国家卫健委 · 政策解读", "https://www.nhc.gov.cn/zwgk/zcjd/list.shtml"),
    ("国家卫健委 · 通知公告", "https://www.nhc.gov.cn/zwgk/wtzgg/list.shtml"),
]


def pubmed(term=PUBMED_TERM, n=12):
    search = f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&retmax={n}&sort=date&term={urllib.parse.quote(term)}"
    ids = http_json(search, timeout=30)["esearchresult"]["idlist"]
    if not ids:
        return []
    summ = f"{EUTILS}/esummary.fcgi?db=pubmed&retmode=json&id={','.join(ids)}"
    data = http_json(summ, timeout=30)["result"]
    out = []
    for i in ids:
        d = data.get(i, {})
        out.append({
            "title": clean(d.get("title", "")),
            "source": clean(d.get("source", "")),
            "date": clean(d.get("pubdate", "")),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{i}/",
        })
    return out


def rss(url, n=12):
    xml = http_get(url, timeout=30)
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    out = []
    for it in items[:n]:
        def g(tag):
            m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", it, re.S)
            return clean(re.sub(r"<.*?>", "", m.group(1))) if m else ""
        out.append({"title": g("title"), "date": g("pubDate")[:16],
                    "url": g("link"), "desc": g("description")})
    return out


def nhc(name, url, n=10):
    html = http_get(url, timeout=30)
    # 匹配链接标题与日期，结构变化时会自然失败并被上层捕获
    pat = re.compile(r'href="(/\w+/\w+/[a-z0-9]+\.shtml)"[^>]*>([^<]{6,80})</a>.*?(\d{4}-\d{2}-\d{2})', re.S)
    out, seen = [], set()
    for m in pat.finditer(html):
        href, title, date = m.group(1), clean(m.group(2)), m.group(3)
        link = "https://www.nhc.gov.cn" + href
        if link in seen:
            continue
        seen.add(link)
        out.append({"title": title, "date": date, "url": link})
        if len(out) >= n:
            break
    return out


def table(rows, cols=("title", "date", "url")):
    lines = ["| 标题 | 日期 | 链接 |", "|---|---|---|"]
    for r in rows:
        t = clean(r.get("title", ""), 90)
        lines.append(f"| {t} | {r.get('date', '')} | [原文]({r.get('url', '')}) |")
    lines.append("")
    return lines


def main():
    date = today()
    lines = []

    lines.append("## 临床指南更新（PubMed）\n")
    try:
        rows = pubmed()
        lines += table(rows) if rows else ["_无新增。_\n"]
    except Exception as e:
        lines.append(f"_抓取失败：{e}_\n")

    lines.append("## 国家卫健委动态\n")
    got = False
    for name, url in NHC_URLS:
        try:
            rows = nhc(name, url)
            if rows:
                got = True
                lines.append(f"**{name}**\n")
                lines += table(rows)
        except Exception as e:
            lines.append(f"_{name} 抓取失败：{e}_\n")
    if not got:
        lines.append("_源站结构可能已变化，可在 scripts/fetch_policy.py 里调整解析规则。_\n")

    lines.append("## WHO 卫生要闻\n")
    try:
        rows = rss(WHO_RSS, 8)
        lines += table(rows) if rows else ["_无新增。_\n"]
    except Exception as e:
        lines.append(f"_抓取失败：{e}_\n")

    extra = os.environ.get("POLICY_RSS", "").strip()
    if extra:
        for url in [u.strip() for u in extra.split(",") if u.strip()]:
            lines.append(f"## 自定义源：{url}\n")
            try:
                rows = rss(url, 10)
                lines += table(rows) if rows else ["_无新增。_\n"]
            except Exception as e:
                lines.append(f"_抓取失败：{e}_\n")

    lines.append("---\n")
    lines.append("数据来源：PubMed E-utilities · 国家卫健委 · WHO RSS · 自定义 RSS。"
                 "相关主线：[[医疗/index|医疗]] · [[医疗/政策法规|政策法规]]")
    write_note(f"daily/policy/{date}.md", f"医疗政策与指南 {date}",
               ["情报", "医疗", "政策"], lines,
               description="每日医疗政策、指南与行业动态汇总")


if __name__ == "__main__":
    main()
