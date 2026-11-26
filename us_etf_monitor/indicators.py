"""技术指标。RSI 用 Wilder 平滑，与 TradingView、富途、老虎等主流软件口径一致。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI = SMA(MAX(涨幅,0),N,1) / SMA(ABS(涨跌),N,1) × 100，即 Wilder 平滑。"""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 * up / (up + dn)
    return out.where((up + dn) > 0, 50.0)


def macd(close: pd.Series, fast=12, slow=26, sig=9):
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=sig, adjust=False).mean()
    return dif, dea, 2 * (dif - dea)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def streak(cond: pd.Series) -> pd.Series:
    """条件连续成立的天数（不成立为 0）。"""
    c = cond.fillna(False).astype(bool)
    grp = (~c).cumsum()
    return c.groupby(grp).cumsum().astype(int)


def enrich(df: pd.DataFrame, vol_scale: float = 1.0) -> pd.DataFrame:
    """在行情上加全部指标列。vol_scale：午盘时把最后一根的半日成交量折算成全天。"""
    d = df.copy()
    c = d["close"]
    d["vol_adj"] = d["volume"].astype(float)
    if vol_scale != 1.0:
        d.iloc[-1, d.columns.get_loc("vol_adj")] *= vol_scale

    d["chg"] = c.pct_change() * 100
    d["rsi"] = rsi(c, C.RSI_N)
    d["rsi2"] = rsi(c, 2)

    for n in sorted(set(C.MA_FAST + C.MA_TREND + (C.MA_LONG,))):
        d[f"ma{n}"] = c.rolling(n).mean()
    a, b, e = (d[f"ma{n}"] for n in C.MA_FAST)
    d["ma_up"] = (a.diff() > 0) & (b.diff() > 0) & (e.diff() > 0)
    d["ma_dn"] = (a.diff() < 0) & (b.diff() < 0) & (e.diff() < 0)
    d["ma_up_days"] = streak(d["ma_up"])
    d["ma_dn_days"] = streak(d["ma_dn"])
    d["ma_aligned"] = (a > b) & (b > e)

    d["vol_ratio"] = d["vol_adj"] / d["volume"].shift(1).rolling(5).mean()

    d["dif"], d["dea"], d["mhist"] = macd(c, *C.MACD)
    d["gc_days"] = streak(d["dif"] > d["dea"])     # 金叉后第几天
    d["dc_days"] = streak(d["dif"] < d["dea"])     # 死叉后第几天

    d["atr"] = atr(d, C.ATR_N)
    d["atr_pct"] = d["atr"] / c * 100
    d["atr_pctl"] = d["atr_pct"].rolling(252, min_periods=60).rank(pct=True)
    d["vol20"] = np.log(c / c.shift(1)).rolling(20).std() * np.sqrt(252) * 100
    d["bias"] = (c / d[f"ma{C.BIAS_N}"] - 1) * 100
    d["bias_atr"] = d["bias"] / d["atr_pct"]            # 乖离是 ATR% 的几倍：跨品种可比
    d["atr_med"] = d["atr_pct"].rolling(252, min_periods=60).median()
    d["gap"] = (d["open"] / c.shift(1) - 1) * 100
    d["gap_atr"] = (d["open"] - c.shift(1)) / d["atr"].shift(1)
    d["chandelier"] = d["high"].rolling(C.CHANDELIER_N).max() - C.CHANDELIER_K * d["atr"]

    d["ath"] = d["high"].cummax()
    d["dd_ath"] = (c / d["ath"] - 1) * 100
    d["high60"] = d["high"].rolling(60, min_periods=20).max()
    d["dd_60"] = (c / d["high60"] - 1) * 100
    d["ret_rs"] = c.pct_change(C.RS_N) * 100
    d["amt_ratio"] = d["amount"].rolling(5).mean() / d["amount"].rolling(60).mean()   # 近 5 日成交额 / 近 60 日

    # ---- 信号布尔序列（当日与历史统计共用同一套定义）----
    d["sig_right"] = ((d["ma_up_days"] >= C.RIGHT_MIN_DAYS) & d["ma_aligned"]
                      & (d["vol_ratio"] >= C.VOL_RATIO_OK) & (c > d[f"ma{C.MA_FAST[-1]}"]))
    d["right_days"] = streak(d["sig_right"])
    d["trg_right"] = d["sig_right"] & ~d["sig_right"].shift(1, fill_value=False)
    for lv in C.RSI_LEVELS:
        below = d["rsi"] < lv
        d[f"trg_l{lv}"] = below & ~below.shift(1, fill_value=False)
        d[f"l{lv}_days"] = streak(below)          # 连续低于该档的天数（模拟盘开户日补单用）
    return d


def forward_stats(d: pd.DataFrame, trigger_col: str, fwd: int = C.FWD_DAYS):
    """历史上该信号首次出现后 fwd 个交易日的收益统计（不含最近 fwd 天，避免未来数据）。"""
    c = d["close"]
    fr = (c.shift(-fwd) / c - 1) * 100
    hits = fr[d[trigger_col] & fr.notna()]
    if len(hits) == 0:
        return dict(n=0)
    return dict(n=int(len(hits)), win=float((hits > 0).mean() * 100),
                avg=float(hits.mean()), worst=float(hits.min()), fwd=fwd)
