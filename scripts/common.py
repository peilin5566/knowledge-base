# -*- coding: utf-8 -*-
"""公共工具：HTTP 请求、日期、写笔记。仅使用 Python 标准库，无需安装依赖。"""
import os
import re
import ssl
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def http_get(url, timeout=30, headers=None, retries=2):
    """返回 str；失败抛异常。带简单重试，避免偶发超时导致整篇失败。"""
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
                raw = r.read()
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(1.5 * (i + 1))
    raise last


def http_json(url, timeout=30, headers=None):
    return json.loads(http_get(url, timeout=timeout, headers=headers))


def today(fmt="%Y-%m-%d"):
    """默认用 UTC+8（北京时间）"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime(fmt)


def now_str():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


def clean(s, limit=None):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    s = s.replace("|", "｜").replace("[", "(").replace("]", ")")
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def write_note(rel_path, title, tags, lines, description=""):
    """把内容写成 Quartz 可用的 Markdown 笔记"""
    path = os.path.join(CONTENT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tags_md = "\n".join(f"  - {t}" for t in tags)
    body = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            f"title: {title}\n"
            f"date: {today()}\n"
            "tags:\n" + (tags_md + "\n" if tags else "") +
            f"description: {clean(description, 120)}\n"
            "draft: false\n"
            "---\n\n"
            f"# {title}\n\n"
            f"> 自动抓取 · {now_str()}（北京时间）· 数据来源见文末\n\n"
            f"{body}\n"
        )
    print(f"written: {rel_path}")
    return path


def section(title, ok=True):
    icon = "✅" if ok else "⚠️"
    return f"## {icon} {title}\n"
