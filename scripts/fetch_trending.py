# -*- coding: utf-8 -*-
"""科技开源趋势：抓取 GitHub Trending，生成每日热门项目笔记。

在 workflow env 里设置 LANGS 可指定语言，例如 "python,typescript"（留空为全语言）。
"""
import sys, os, re, html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http_get, today, clean, write_note  # noqa: E402

BASE = "https://github.com/trending"


def strip_tags(s):
    return clean(html.unescape(re.sub(r"<.*?>", "", s)))


def trending(lang=None):
    url = f"{BASE}/{lang}" if lang else BASE
    page = http_get(url, timeout=40)
    out = []
    for block in re.split(r'<article class="Box-row"', page)[1:]:
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.S)
        if not h2:
            continue
        hrefs = re.findall(r'href="/([^"]+)"', h2.group(1))
        repo = next((h.strip() for h in hrefs if h.count("/") == 1 and "." not in h), None)
        if not repo:
            continue
        d = re.search(r"<p[^>]*color-fg-muted[^>]*>(.*?)</p>", block, re.S)
        desc = strip_tags(d.group(1)) if d else ""
        lang_m = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
        st = re.search(r'stargazers"[^>]*>(.*?)</a>', block, re.S)
        td = re.search(r"([\d,]+)\s*stars today", block)
        out.append({
            "repo": repo,
            "desc": desc,
            "lang": clean(lang_m.group(1)) if lang_m else "—",
            "stars": strip_tags(st.group(1)) if st else "—",
            "today": td.group(1) + " stars today" if td else "—",
        })
    return out


def main():
    date = today()
    langs = [l.strip() for l in os.environ.get("LANGS", "").split(",") if l.strip()]
    if not langs:
        langs = [None]
    lines = []
    all_items = []
    for lang in langs:
        head = f"## GitHub Trending{' · ' + lang if lang else '（全语言）'}\n"
        try:
            items = trending(lang)
            all_items += items
            if not items:
                lines += [head, "_未解析到条目（页面结构可能已变化）。_\n"]
                continue
            lines += [head, "| 项目 | 语言 | 简介 | 今日 |", "|---|---|---|---|"]
            for it in items[:15]:
                name = it["repo"]
                lines.append(f"| [{name}](https://github.com/{name}) | {it['lang']} | "
                             f"{clean(it['desc'], 90)} | {it['today']} |")
            lines.append("")
        except Exception as e:
            lines += [head, f"_抓取失败：{clean(str(e), 80)}_\n"]

    if all_items:
        lines.append("### 值得单独记一笔\n")
        lines.append("- ")
        lines.append("")

    lines.append("---\n")
    lines.append("数据来源：[GitHub Trending](https://github.com/trending)。"
                 "相关主线：[[科技/index|科技]] · [[科技/产业观察|产业观察]] · "
                 "[[人工智能/index|人工智能]]")
    write_note(f"daily/trending/{date}.md", f"科技开源趋势 {date}",
               ["情报", "科技", "开源"], lines,
               description="每日 GitHub Trending 热门开源项目")


if __name__ == "__main__":
    main()
