# -*- coding: utf-8 -*-
"""金融行情日报：贵金属 + 加密资产 + 主要股票指数，生成每日盘面快照。

多源兜底：指数/贵金属优先 Yahoo Finance，失败回退 Stooq；加密优先 CoinGecko，回退 Coinbase。
任一源失败只在对应单元格标注，不影响整篇生成。

数据仅为行情记录，不构成投资建议。
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http_get, http_json, today, clean, write_note  # noqa: E402

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# 显示名 → (Yahoo 代码, Stooq 代码)
TARGETS = [
    ("黄金（美元/盎司）", "GC=F", "xauusd"),
    ("白银（美元/盎司）", "SI=F", "xagusd"),
    ("标普 500", "^GSPC", "^spx"),
    ("纳斯达克综合", "^IXIC", "^ndq"),
    ("恒生指数", "^HSI", "^hsi"),
    ("上证指数", "000001.SS", "^shc"),
    ("深证成指", "399001.SZ", "^szse"),
]

COINS = [("比特币 BTC", "bitcoin", "BTC-USD"), ("以太坊 ETH", "ethereum", "ETH-USD")]


def yahoo(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
    d = http_json(url, timeout=30, headers=HEADERS)
    res = d["chart"]["result"][0]["meta"]
    price = res.get("regularMarketPrice") or res.get("previousClose")
    prev = res.get("chartPreviousClose") or res.get("previousClose")
    if price is None:
        raise ValueError("no price")
    chg = ((price - prev) / prev * 100) if prev else None
    return price, chg


def stooq(sym):
    txt = http_get(f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv", timeout=30)
    rows = [r for r in txt.strip().splitlines() if r]
    if len(rows) < 2:
        raise ValueError("empty csv")
    cols = rows[1].split(",")
    # Symbol,Date,Time,Open,High,Low,Close,Volume
    close = float(cols[6])
    open_ = float(cols[3])
    chg = ((close - open_) / open_ * 100) if open_ else None
    return close, chg


def quote(y_sym, s_sym):
    """返回 (price, change, source)"""
    for name, fn, sym in (("Yahoo", yahoo, y_sym), ("Stooq", stooq, s_sym)):
        try:
            p, c = fn(sym)
            return p, c, name
        except Exception:
            continue
    return None, None, "获取失败"


def crypto():
    """返回 [(名称, 价格, 24h涨幅, 数据源)]"""
    try:
        ids = ",".join(c[1] for c in COINS)
        d = http_json("https://api.coingecko.com/api/v3/simple/price"
                      f"?ids={ids}&vs_currencies=usd&include_24hr_change=true",
                      timeout=30, headers=HEADERS)
        return [(n, d.get(i, {}).get("usd"), d.get(i, {}).get("usd_24h_change"), "CoinGecko")
                for n, i, _p in COINS]
    except Exception:
        pass
    out = []
    for n, _i, pair in COINS:
        try:
            d = http_json(f"https://api.coinbase.com/v2/prices/{pair}/spot",
                          timeout=25, headers=HEADERS)
            out.append((n, float(d["data"]["amount"]), None, "Coinbase"))
        except Exception:
            out.append((n, None, None, "获取失败"))
    return out


def fmt(v, pct=False):
    if v is None:
        return "—"
    return f"{v:+.2f}%" if pct else f"{v:,.2f}"


def main():
    date = today()
    lines = []

    lines.append("## 贵金属\n")
    lines += ["| 品种 | 价格 | 涨跌 | 数据源 |", "|---|---|---|---|"]
    for name, ys, ss in TARGETS[:2]:
        p, c, src = quote(ys, ss)
        lines.append(f"| {name} | {fmt(p)} | {fmt(c, pct=True)} | {src} |")
    lines.append("")

    lines.append("## 加密资产（美元）\n")
    lines += ["| 资产 | 价格 | 24h | 数据源 |", "|---|---|---|---|"]
    for n, p, c, src in crypto():
        lines.append(f"| {n} | {fmt(p)} | {fmt(c, pct=True)} | {src} |")
    lines.append("")

    lines.append("## 股票指数\n")
    lines += ["| 指数 | 点位 | 涨跌 | 数据源 |", "|---|---|---|---|"]
    for name, ys, ss in TARGETS[2:]:
        p, c, src = quote(ys, ss)
        lines.append(f"| {name} | {fmt(p)} | {fmt(c, pct=True)} | {src} |")
    lines.append("")

    lines.append("## 今日观察\n")
    lines.append("- ")
    lines.append("- ")
    lines.append("")
    lines.append("---\n")
    lines.append("数据源：Yahoo Finance（主）/ Stooq（备）/ CoinGecko（主）/ Coinbase（备）。"
                 "相关主线：[[金融/index|金融]] · [[金融/资产配置|资产配置]] · "
                 "[[金融/交易复盘|交易复盘]]")
    lines.append("\n> 本页仅为行情记录，不构成任何投资建议。")
    write_note(f"daily/markets/{date}.md", f"金融行情日报 {date}",
               ["情报", "金融", "行情"], lines,
               description="每日多市场行情快照：贵金属、加密、主要股指")


if __name__ == "__main__":
    main()
