"""宏观事件与指数成分调整日历。

日期来源（2026-11 查询，官方每年公布一次，每年 1 月补下一年）：
- FOMC：美联储 2026-11-12 公布的修订版 2027 日程（10 月会议只讨论策略、不出利率决议，已剔除）
  https://www.federalreserve.gov/newsevents/pressreleases/monetary20261112a.htm
- CPI：https://www.bls.gov/schedule/news_release/cpi.htm
- 非农：https://www.bls.gov/schedule/news_release/empsit.htm
- 罗素重构：https://www.lseg.com/en/media-centre/press-releases/ftse-russell/2026/ftse-russell-announces-december-2026-russell-us-indexes-reconstitution-schedule
"""
from __future__ import annotations

from datetime import date, timedelta

# 只记"出结果那一天"（美东时间）
FOMC = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
        "2027-07-28", "2027-09-15", "2027-11-17"]
CPI = ["2026-12-10", "2027-01-13", "2027-02-11", "2027-03-10", "2027-04-13", "2027-05-12",
       "2027-06-10", "2027-07-14", "2027-08-11", "2027-09-14", "2027-10-14", "2027-11-10",
       "2027-12-10"]
NFP = ["2026-12-04", "2027-01-08", "2027-02-05", "2027-03-05", "2027-04-02", "2027-05-07",
       "2027-06-04", "2027-07-02", "2027-08-06", "2027-09-03", "2027-10-08", "2027-11-05",
       "2027-12-03"]

MACRO = ([(d, "FOMC 利率决议", "美东 14:00 公布，北京时间次日凌晨") for d in FOMC]
         + [(d, "CPI 通胀数据", "美东 08:30 开盘前公布") for d in CPI]
         + [(d, "非农就业数据", "美东 08:30 开盘前公布") for d in NFP])

# 指数成分调整（"优胜劣汰"生效日，收盘后生效）。codes = 受影响的池内 ETF
RECON_FIXED = [
    ("2026-12-11", "罗素指数半年度重构", ["IWM"]),
]


def third_friday(y: int, m: int) -> date:
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def recon_events(start: date, end: date):
    """按规则生成的成分调整日：标普/行业 SPDR 季度再平衡、纳指 12 月重构、SCHD 3 月重构、SMH 3/9 月审核。"""
    out = [(date.fromisoformat(d), t, c) for d, t, c in RECON_FIXED]
    spdr = ["SPY", "XLF", "XLV", "XLE", "XLY", "XLI", "XLU", "XLP", "XLC", "XLRE"]
    for y in range(start.year, end.year + 1):
        for m in (3, 6, 9, 12):
            f = third_friday(y, m)
            out.append((f, "标普及行业 SPDR 季度再平衡", spdr + ["XBI", "KRE"]))
        out.append((third_friday(y, 12), "纳指100年度重构", ["QQQ"]))
        out.append((third_friday(y, 3), "SCHD 年度重构（指数在 3 月重选 100 只成分）", ["SCHD"]))
        for m in (3, 9):
            out.append((third_friday(y, m), "SMH 指数半年度审核", ["SMH"]))
        if y >= 2027:   # 2027 起罗素也是 6 月、12 月的第二个周五（按 2026 年规则推算，以官方公告为准）
            for m in (6, 12):
                f = third_friday(y, m) - timedelta(days=7)
                out.append((f, "罗素指数半年度重构（推算）", ["IWM"]))
    return [e for e in out if start <= e[0] <= end]


def upcoming(today: date, days: int = 10, codes=None):
    """未来 days 个自然日内的事件，按日期排序。codes 给定时只保留与池子相关的成分调整。"""
    end = today + timedelta(days=days)
    ev = []
    for d, title, note in MACRO:
        dd = date.fromisoformat(d)
        if today <= dd <= end:
            ev.append(dict(date=dd, kind="macro", title=title, note=note, codes=[]))
    for dd, title, cs in recon_events(today, end):
        cs = [c for c in cs if codes is None or c in codes]
        if cs:
            ev.append(dict(date=dd, kind="recon", title=title, note="收盘后生效", codes=cs))
    return sorted(ev, key=lambda e: (e["date"], e["kind"]))


def macro_soon(today: date, trading_days: list[date], n: int = 2) -> list[str]:
    """接下来 n 个交易日（含今天之后）内是否有宏观大事件，返回事件名列表。"""
    nxt = [d for d in trading_days if d > today][:n]
    hit = []
    for d, title, _ in MACRO:
        if date.fromisoformat(d) in nxt:
            hit.append(f"{date.fromisoformat(d).strftime('%m-%d')} {title}")
    return hit
