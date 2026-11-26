"""行情数据层：三个数据源自动降级 + 本地缓存增量更新 + 演示数据。

统一输出 DataFrame：index=日期，列 open/high/low/close/volume/amount，按日期升序。
- 价格是"税后复权价"：拆股已调整，分红按 (1-预扣税) 再投入（config.DIV_WITHHOLD）。
  这样历史高点、回撤、回测收益都可比，且贴近中国投资者的真实到手收益。
- 缓存里存的是"原始价 + 每股分红"，每次运行在本地重新复权，所以只需拉最近几天的增量。
"""
from __future__ import annotations

import io
import os
import random
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import config as C

NY = ZoneInfo("America/New_York")
BJ = ZoneInfo("Asia/Shanghai")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
RAW = ["open", "high", "low", "close", "volume", "div"]
COLS = ["open", "high", "low", "close", "volume", "amount"]
SOURCE_CN = {"yfinance": "Yahoo", "tiingo": "Tiingo", "stooq": "Stooq",
             "cache": "本地缓存(过期)", "demo": "演示数据"}


class DataError(Exception):
    pass


def now_ny() -> datetime:
    return datetime.now(NY)


# ------------------------------------------------------------------ 交易日历
_CAL = None


def calendar():
    """纽交所日历（含感恩节、圣诞等休市和半天市）。没装 exchange_calendars 时退化为工作日。"""
    global _CAL
    if _CAL is None:
        try:
            import exchange_calendars as xc
            _CAL = xc.get_calendar("XNYS")
        except Exception:  # noqa: BLE001
            _CAL = False
    return _CAL or None


def is_session(d: date) -> bool:
    cal = calendar()
    if cal is None:
        return d.weekday() < 5
    return bool(cal.is_session(pd.Timestamp(d)))


def close_minute(d: date) -> int:
    """当天收盘时刻（美东，距 0 点分钟数）。半天市 13:00，正常 16:00。"""
    cal = calendar()
    if cal is None or not cal.is_session(pd.Timestamp(d)):
        return 16 * 60
    t = cal.session_close(pd.Timestamp(d)).tz_convert(NY)
    return t.hour * 60 + t.minute


def session_open_bj(d: date) -> str:
    """某交易日 9:30 ET 开盘对应的北京时间，如 "11-27 周五 22:30"（夏令时）/ "23:30"（冬令时）。"""
    t = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY).astimezone(BJ)
    return t.strftime("%m-%d ") + "一二三四五六日"[t.weekday()].join(["周", ""]) + t.strftime(" %H:%M")


def next_sessions(d: date, n: int = 5) -> list[date]:
    cal = calendar()
    if cal is None:
        return [x.date() for x in pd.bdate_range(d, periods=n + 1)][1:]
    s = cal.sessions_in_range(pd.Timestamp(d), pd.Timestamp(d) + pd.Timedelta(days=n * 2 + 7))
    return [x.date() for x in s if x.date() > d][:n]


# ------------------------------------------------------------------ 复权
def adjust(raw: pd.DataFrame, withhold: float = C.DIV_WITHHOLD) -> pd.DataFrame:
    """原始价（已拆股调整）+ 每股分红 -> 税后复权价。

    除息日 t 的复权因子：对 t 之前的所有价格乘以 (1 - 净分红 / 前收)，净分红 = 分红 × (1-预扣税)。
    成交量不变；成交额用原始收盘价 × 成交量，反映真实成交金额。
    """
    d = raw.copy()
    div = d["div"].fillna(0.0) * (1 - withhold)
    pc = d["close"].shift(1)
    step = (1 - div / pc).where(div > 0, 1.0).fillna(1.0)
    factor = step[::-1].cumprod()[::-1].shift(-1, fill_value=1.0)
    out = pd.DataFrame(index=d.index)
    for c in ["open", "high", "low", "close"]:
        out[c] = d[c] * factor
    out["volume"] = d["volume"].astype(float)
    out["amount"] = d["close"] * d["volume"]
    return out


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=RAW)
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    for c in RAW:
        if c not in df:
            df[c] = 0.0 if c == "div" else np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[RAW].dropna(subset=["close"])
    df = df[(df["close"] > 0) & (df["high"] > 0) & (df["low"] > 0)]
    df["div"] = df["div"].fillna(0.0)
    return df[~df.index.duplicated(keep="last")].sort_index()


# ------------------------------------------------------------------ 解析器（可单测）
def parse_yf_frame(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance download(auto_adjust=False, actions=True) 单只代码的结果。Close 已按拆股调整。"""
    if df is None or df.empty:
        return _clean(pd.DataFrame())
    m = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume",
         "Dividends": "div"}
    return _clean(df.rename(columns=m))


def parse_tiingo(rows: list) -> pd.DataFrame:
    """Tiingo daily prices JSON。用 adj* 字段（Tiingo 已含拆股与全额分红复权），div 记 0 不再二次复权。"""
    recs = [dict(date=r["date"][:10], open=r.get("adjOpen"), high=r.get("adjHigh"), low=r.get("adjLow"),
                 close=r.get("adjClose"), volume=r.get("adjVolume") or r.get("volume"), div=0.0)
            for r in rows or []]
    if not recs:
        return _clean(pd.DataFrame())
    return _clean(pd.DataFrame(recs).set_index("date"))


def parse_stooq(text: str) -> pd.DataFrame:
    """Stooq CSV：Date,Open,High,Low,Close,Volume（Stooq 已做拆股与分红调整）。"""
    if not text or not text.startswith("Date"):
        return _clean(pd.DataFrame())
    df = pd.read_csv(io.StringIO(text))
    df = df.rename(columns=str.lower).set_index("date")
    df["div"] = 0.0
    return _clean(df)


# ------------------------------------------------------------------ 三个数据源
def _get(url, params=None):
    import requests

    last = None
    for i in range(C.REQUEST_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=C.REQUEST_TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (i + 1))
        finally:
            time.sleep(random.uniform(*C.REQUEST_PAUSE))
    raise DataError(f"请求失败 {url}: {last}")


def fetch_yf_batch(codes: list[str], start: str) -> dict[str, pd.DataFrame]:
    """一次请求拉全部代码。失败的代码不在返回值里。"""
    import yfinance as yf

    out = {}
    for attempt in range(3):
        try:
            df = yf.download(codes, start=start, auto_adjust=False, actions=True, group_by="ticker",
                             threads=False, progress=False, timeout=C.REQUEST_TIMEOUT)
            break
        except Exception as e:  # noqa: BLE001  限频时等一会儿再来
            print(f"[warn] yfinance 第 {attempt + 1} 次失败: {e}")
            time.sleep(10 * (attempt + 1))
    else:
        return out
    if df is None or df.empty:
        return out
    for c in codes:
        try:
            sub = df[c] if isinstance(df.columns, pd.MultiIndex) else df
            p = parse_yf_frame(sub.dropna(how="all"))
            if len(p):
                out[c] = p
        except KeyError:
            pass
    return out


_TIINGO = dict(used=0, blocked=False)


def fetch_tiingo(code: str, start: str) -> pd.DataFrame:
    """免费版额度：每小时 50 次、每天 1000 次。一次运行最多用 TIINGO_MAX_CALLS 次，碰到限额就停用到本次结束。"""
    key = os.environ.get("TIINGO_KEY")
    if not key:
        raise DataError("未设置 TIINGO_KEY")
    if code.startswith("^"):
        raise DataError("Tiingo 没有指数行情")
    if _TIINGO["blocked"] or _TIINGO["used"] >= C.TIINGO_MAX_CALLS:
        raise DataError("Tiingo 本次运行额度已用完")
    _TIINGO["used"] += 1
    import requests
    r = requests.get(f"https://api.tiingo.com/tiingo/daily/{code.lower()}/prices",
                     params=dict(startDate=start, token=key, format="json"), headers=UA, timeout=C.REQUEST_TIMEOUT)
    if r.status_code == 429 or "limit" in r.text[:200].lower():
        _TIINGO["blocked"] = True
        raise DataError("Tiingo 额度已满，本次不再请求")
    r.raise_for_status()
    return parse_tiingo(r.json())


def fetch_stooq(code: str, start: str) -> pd.DataFrame:
    sym = code.lower().replace("^", "") + (".us" if not code.startswith("^") else "")
    r = _get("https://stooq.com/q/d/l/", params=dict(s=sym, i="d", d1=start.replace("-", "")))
    return parse_stooq(r.text)


# ------------------------------------------------------------------ 缓存 + 增量
def _cache_path(cache_dir: Path, code: str) -> Path:
    return cache_dir / f"{code.replace('^', '_')}.csv"


def load_cache(cache_dir: Path | None, code: str) -> pd.DataFrame | None:
    if cache_dir is None or not _cache_path(cache_dir, code).exists():
        return None
    df = pd.read_csv(_cache_path(cache_dir, code), index_col=0, parse_dates=True)
    return _clean(df)


def merge(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return new
    both = pd.concat([old[old.index < new.index[0]], new])
    return both[~both.index.duplicated(keep="last")].sort_index()


def fetch_all(codes: list[str], cache_dir: Path | None, want: date | None):
    """返回 ({code: 复权后 df}, {code: 来源}, [问题说明])。

    1. 有缓存的代码只拉最近 10 天（足够覆盖节假日），没缓存的从 HISTORY_START 拉起；
    2. yfinance 一次批量；缺的或没更新到 want 的，逐只试 Tiingo、Stooq；
    3. 全部失败用旧缓存并在报告顶部提示。
    """
    caches = {c: load_cache(cache_dir, c) for c in codes}
    starts = {}
    for c, old in caches.items():
        starts[c] = (old.index[-10].strftime("%Y-%m-%d") if old is not None and len(old) > 30
                     else C.HISTORY_START)
    raw, src, problems = {}, {}, []

    groups: dict[str, list[str]] = {}
    for c, s in starts.items():
        groups.setdefault(s if s == C.HISTORY_START else "inc", []).append(c)
    for g, cs in groups.items():
        s = C.HISTORY_START if g == C.HISTORY_START else min(starts[c] for c in cs)
        got = fetch_yf_batch(cs, s) if "yfinance" in C.SOURCES else {}
        for c, df in got.items():
            raw[c], src[c] = merge(caches[c], df), "yfinance"

    def stale(c):
        return c not in raw or (want is not None and raw[c].index[-1].date() < want)

    for c in [c for c in codes if stale(c)]:
        for s_name, fn in (("tiingo", fetch_tiingo), ("stooq", fetch_stooq)):
            if s_name not in C.SOURCES:
                continue
            try:
                # 这两个源给的是已复权价，不能和缓存里的原始价拼接，所以整段拉取、整段替换
                full = fn(c, C.HISTORY_START)
                if len(full) == 0:
                    continue
                if c not in raw or full.index[-1] > raw[c].index[-1]:
                    raw[c], src[c] = full, s_name
                if not stale(c):
                    break
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {c} {s_name}: {e}")

    out = {}
    for c in codes:
        if c in raw and len(raw[c]) >= 30:
            if cache_dir and src[c] == "yfinance":
                cache_dir.mkdir(parents=True, exist_ok=True)
                raw[c].to_csv(_cache_path(cache_dir, c))
            out[c] = adjust(raw[c]) if src[c] == "yfinance" else adjust(raw[c], 0.0)
        elif caches[c] is not None and len(caches[c]) >= 30:
            out[c], src[c] = adjust(caches[c]), "cache"
        else:
            problems.append(f"{c} 所有数据源都取不到，已从本期报告剔除")
    return out, src, problems


# ------------------------------------------------------------------ 演示数据
def demo_history(code: str, idx: int, asof: str = "2026-11-24", n: int = 1500) -> pd.DataFrame:
    """无网络时用的模拟行情（几何随机游走 + 人为构造的尾部形态）。绝非真实价格。"""
    seed = sum(ord(ch) * (i + 1) for i, ch in enumerate(code))
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=asof, periods=n)
    hv = any(p["code"] == code and "hv" in p["flags"] for p in C.POOL)
    vol = rng.uniform(0.018, 0.03) if hv else rng.uniform(0.007, 0.016)
    if code == C.VIX_CODE:
        lvl = 16 + np.cumsum(rng.normal(0, 0.6, n))
        lvl = np.clip(lvl - (lvl - 17) * 0.03, 10, 45)
        lvl[-5:] += np.linspace(0, 6, 5)
        df = pd.DataFrame(dict(open=lvl, high=lvl * 1.04, low=lvl * 0.96, close=lvl, volume=0.0, div=0.0),
                          index=dates)
        df.index.name = "date"
        return adjust(df)
    ret = rng.normal(rng.uniform(0.0001, 0.0006), vol, n)
    shape = idx % 7
    if shape == 0:      # 连续急跌 -> 深度超卖
        ret[-7:] = -np.abs(rng.normal(vol * 1.1, vol * 0.3, 7))
    elif shape == 1:    # 底部放量三连阳 -> 右侧启动
        ret[-20:-4] = rng.normal(-0.001, vol * 0.4, 16)
        ret[-4:] = np.abs(rng.normal(vol * 0.9, vol * 0.2, 4))
    elif shape == 2:    # 持续拉升 -> 超买
        ret[-9:] = np.abs(rng.normal(vol * 0.7, vol * 0.2, 9))
    elif shape == 3:    # 阴跌 -> 接近超卖
        ret[-8:] = -np.abs(rng.normal(vol * 0.45, vol * 0.15, 8))
    close = rng.uniform(20, 500) * np.exp(np.cumsum(ret))
    spread = np.abs(rng.normal(0, vol * 0.5, n))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, vol * 0.3, n))
    high = np.maximum.reduce([close * (1 + spread), open_, close])
    low = np.minimum.reduce([close * (1 - spread), open_, close])
    volume = rng.uniform(2e6, 6e7) * np.exp(rng.normal(0, 0.25, n)) * (1 + 12 * np.abs(ret))
    if shape == 1:
        volume[-4:] *= 2.2
    div = np.zeros(n)
    if any(p["code"] == code and "div" in p["flags"] for p in C.POOL) or code in ("SCHD", "SPY", "TLT"):
        div[::63] = close[::63] * 0.008          # 每季度分一次约 0.8%
    df = pd.DataFrame(dict(open=open_, high=high, low=low, close=close, volume=volume, div=div),
                      index=dates)
    df.index.name = "date"
    return adjust(df.round(4))
