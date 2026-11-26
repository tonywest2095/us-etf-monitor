"""模拟盘：把日报的左侧 / 右侧 / 高抛信号自动变成虚拟交易，生成收益看板 docs/sim.html。

执行口径（尽量贴近真人照着日报操作）：
- 只在收盘那次运行（session=close）做决策，用的是全天完整数据；
- 订单在下一个交易日的开盘价成交（第二天盘中那次运行时补记），买入价上浮、卖出价下浮一个滑点；
- 美股没有涨跌停：开盘跳空低开时，止损单就按开盘价成交，不假设能在止损价卖出；
- 盘中那次只做两件事：按今天开盘价成交昨晚的订单 + 按盘中价更新市值。
实盘（docs/sim/state.json）与历史回测（docs/sim/backtest.json）用的是同一个 decide()，规则完全一致。
"""
from __future__ import annotations

import json
import math
from datetime import date as Date
from html import escape as E
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

from .signals import temp_score, vol_group

HV = {p["code"] for p in C.POOL if "hv" in p["flags"]}


def tranche_cum(group: str) -> list:
    t = C.LEFT_TRANCHES[group]
    return [sum(t[:i + 1]) for i in range(len(t))]


def max_pos(code: str) -> float:
    return C.SIM_MAX_POS_HV if code in HV else C.SIM_MAX_POS


def slip(code: str) -> float:
    return C.SIM_SLIP[C.tier_of(code)]


def _n(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def _r(x, nd=3):
    return None if _n(x) else round(float(x), nd)


def _days(a: str, b: str) -> int:
    """a、b 两个日期之间的交易日数（按工作日近似，不扣节假日）。"""
    return int(np.busday_count(a, b))


# ============================================================================ 状态
def new_state(start: str, cash: float = C.SIM_CASH) -> dict:
    return dict(start=start, cash0=cash, cash=cash, positions={}, pending=[], trades=[], closed=[],
                nav=[], base={}, last_decide=None)


def equity(st, px: dict) -> float:
    return st["cash"] + sum(p["shares"] * px.get(c, p["last_px"]) for c, p in st["positions"].items())


# ============================================================================ 成交
def fill(st, bars: dict, names: dict, today: str):
    """bars: code -> dict(date, open, prev_close)。用 decision 之后第一根 K 线的开盘价成交，先卖后买。"""
    keep = []
    orders = sorted(st["pending"], key=lambda o: (o["side"] != "sell", -o.get("prio", 0)))
    for o in orders:
        c, b = o["code"], bars.get(o["code"])
        if b is None or b["date"] <= o["date"] or _n(b["open"]):
            if _days(o["date"], today) <= 5:          # 停牌 / 数据没更新：最多等 5 个交易日
                keep.append(o)
            continue
        op, pc = float(b["open"]), float(b["prev_close"])
        if o["side"] == "sell":
            p = st["positions"].get(c)
            if p is None:
                continue
            sh = p["shares"] if o["shares"] == "all" else min(int(o["shares"]), p["shares"])
            px = op * (1 - slip(c))
            amt = sh * px
            fee = amt * (C.SIM_FEE + C.SIM_SELL_FEE)
            avg = p["cost"] / p["shares"]
            pnl = amt - fee - avg * sh
            st["cash"] += amt - fee
            p["cost"] -= avg * sh
            p["shares"] -= sh
            p["realized"] += pnl
            st["trades"].append(dict(date=b["date"], code=c, name=names.get(c, c), side="卖出", px=_r(px),
                                     shares=sh, amount=round(amt, 2), fee=round(fee, 2),
                                     pnl=round(pnl, 2), reason=o["reason"]))
            if p["shares"] <= 0:
                st["closed"].append(dict(code=c, name=names.get(c, c), entry=p["entry"], kind=p["kind"],
                                         title=p["title"], exit=b["date"], reason=o["reason"],
                                         days=_days(p["entry"], b["date"]),
                                         pnl=round(p["realized"], 2),
                                         ret=round(p["realized"] / p["invested"] * 100, 2)))
                del st["positions"][c]
        else:
            px = op * (1 + slip(c))
            budget = min(o["amount"], st["cash"] / (1 + C.SIM_FEE))
            sh = int(budget / px / C.SIM_LOT) * C.SIM_LOT
            if sh <= 0 or sh * px < min(C.SIM_MIN_ORDER / 2, o["amount"] * 0.5):
                continue
            amt = sh * px
            fee = amt * C.SIM_FEE
            st["cash"] -= amt + fee
            p = st["positions"].get(c)
            if p is None:
                p = st["positions"][c] = dict(shares=0, cost=0.0, invested=0.0, realized=0.0, entry=b["date"],
                                              took=[], trail=False, last_px=px, hh=px, **o["meta"])
            else:
                p.update({k: v for k, v in o["meta"].items() if k in ("grade", "stop", "title")})
            tb = p.get("today_buy")
            if not tb or tb[0] != b["date"]:
                tb = p["today_buy"] = [b["date"], 0, 0.0]
            tb[1] += sh
            tb[2] += amt + fee
            p["shares"] += sh
            p["cost"] += amt + fee
            p["invested"] += amt + fee
            p["last_add"] = px
            st["trades"].append(dict(date=b["date"], code=c, name=names.get(c, c), side="买入", px=_r(px),
                                     shares=sh, amount=round(amt, 2), fee=round(fee, 2), pnl=None,
                                     reason=o["reason"]))
    st["pending"] = keep


# ============================================================================ 记账
def mark(st, px: dict, today: str, intraday: bool, bench_code: str, prev: dict | None = None):
    prev = prev or {}
    for c, p in st["positions"].items():
        if c in px:
            p["last_px"] = px[c]
        tb = p.get("today_buy") or [None, 0, 0.0]
        sh_b, amt_b = (tb[1], tb[2]) if tb[0] == today else (0, 0.0)
        ref = prev.get(c)
        old = p["shares"] - sh_b
        # 当日盈亏 = 昨天就有的份额 ×（现价 − 昨收）+ 今天新买的份额按成交成本算
        p["day_pnl"] = round((old * (p["last_px"] - ref) if ref and old > 0 else 0.0)
                             + (sh_b * p["last_px"] - amt_b), 2)
        p["float_pnl"] = round(p["shares"] * p["last_px"] - p["cost"], 2)
    eq = equity(st, px)
    base = st["base"]
    ew = [px[c] / base[c] for c in base if c in px and c != "_bench"]
    b1, b2, wt = C.SIM_BENCH_6040
    before = [x for x in st["nav"] if x["date"] != today]
    m6040 = (before[-1].get("m6040") or 1.0) if before else 1.0
    if before and all(k in px and prev.get(k) for k in (b1, b2)):
        m6040 = round(m6040 * (1 + wt * (px[b1] / prev[b1] - 1) + (1 - wt) * (px[b2] / prev[b2] - 1)), 5)
    row = dict(date=today, equity=round(eq, 2), cash=round(st["cash"], 2), m6040=m6040,
               pos=round((eq - st["cash"]) / eq * 100, 1) if eq else 0,
               bench=round(px[bench_code] / base["_bench"], 5) if bench_code in px and "_bench" in base else None,
               ew=round(float(np.mean(ew)), 5) if ew else None, intraday=intraday)
    if st["nav"] and st["nav"][-1]["date"] == today:
        st["nav"][-1] = row
    else:
        st["nav"].append(row)


# ============================================================================ 决策
def decide(st, rows: dict, names: dict, today: str) -> list:
    """rows: code -> (last, prev)，已 enrich 的两行。按日报同一套规则生成次日开盘的订单。"""
    px = {c: float(r[0].close) for c, r in rows.items()}
    eq = equity(st, px)
    orders, sold = [], set()
    # 平时只在“当天新跌破”那一档买；开户第一天补上最近 3 天内刚出现、日报仍在提示的左侧信号
    look = 3 if st["last_decide"] is None else 1

    # ---------------------------------------------------------------- 卖：止损 / 止盈 / 高抛
    for c, p in list(st["positions"].items()):
        if c not in rows:
            continue
        last, prev = rows[c]
        close = float(last.close)
        held = _days(p["entry"], today)
        avg = p["cost"] / p["shares"]
        # 持仓以来最高价 − 3×ATR：建仓后才开始算的吊灯止盈线（不用建仓前的高点，否则一买就被扫掉）
        p["hh"] = max(p.get("hh") or 0, float(last.high))
        chand = None if _n(last.atr) else p["hh"] - C.CHANDELIER_K * float(last.atr)
        all_why, half_why = None, []

        if p["kind"] == "right" or p["trail"]:
            if chand is not None:
                p["stop"] = max(p["stop"] or 0, chand)          # 吊灯止盈线只上移不下移
        if last.rsi >= C.RSI_OVERBOUGHT[0] and chand is not None:
            p["trail"] = True                                   # 偏热：收紧到吊灯止盈线
            p["stop"] = max(p["stop"] or 0, chand)

        if p["stop"] and close < p["stop"]:
            all_why = "止损（跌破止损价）" if close < avg else "移动止盈（跌破吊灯止盈线）"
        elif (p["kind"] == "left" and not p["trail"] and held >= C.FWD_DAYS and close < last.ma5):
            all_why = f"时间止损（{C.FWD_DAYS} 个交易日仍站不回 MA5）"
        elif (held >= 3 and close < last.chandelier and prev.close >= prev.chandelier
              and not _n(last.ma60) and last.ma60 > rows[c][1].ma60):
            all_why = "破止盈线"
        else:
            if p["kind"] == "left" and "tp1" not in p["took"] and close >= last.ma20:
                half_why.append("反抽到 MA20，先卖一半")
                p["took"].append("tp1")
                p["trail"] = True
                p["stop"] = max(p["stop"] or 0, avg, chand or 0)  # 剩下一半保本 + 移动止盈
            if last.rsi >= C.RSI_OVERBOUGHT[1] and "hot" not in p["took"]:
                half_why.append(f"超买（RSI {last.rsi:.0f}）")
                p["took"].append("hot")
            if last.ma_dn_days >= 2 and last.ret_rs > 5 and "turn" not in p["took"]:
                half_why.append("涨后三线拐头")
                p["took"].append("turn")
            if (1 <= last.dc_days <= C.GC_EARLY and last.dif > 0 and last.dd_60 > -8
                    and "dc" not in p["took"]):
                half_why.append("高位死叉")
                p["took"].append("dc")

        if all_why:
            orders.append(dict(code=c, side="sell", shares="all", reason=all_why, date=today))
            sold.add(c)
        elif half_why:
            half = int(p["shares"] / 2 / C.SIM_LOT) * C.SIM_LOT
            rest = (p["shares"] - half) * close
            sh = "all" if half == 0 or rest < eq * C.SIM_DUST else half
            orders.append(dict(code=c, side="sell", shares=sh, reason="；".join(half_why), date=today))
            sold.add(c)

    # ---------------------------------------------------------------- 买：左侧分档 / 右侧跟随
    buys = []
    score, label, _ = temp_score(r[0] for r in rows.values())
    rs_rank = {c: i + 1 for i, c in enumerate(sorted(rows, key=lambda c: -(0 if _n(rows[c][0].ret_rs)
                                                                             else float(rows[c][0].ret_rs))))}
    cats = {p["code"]: p["cat"] for p in C.POOL}
    for c, (last, prev) in rows.items():
        if c in sold:
            continue
        p = st["positions"].get(c)
        close, atr = float(last.close), float(last.atr)
        above_year = None if _n(last[f"ma{C.MA_LONG}"]) else bool(close > last[f"ma{C.MA_LONG}"])
        high_vol = bool(not _n(last.atr_pctl) and last.atr_pctl >= C.HIGH_VOL_PCTL)
        cap = max_pos(c)
        cum = tranche_cum(vol_group(None if _n(last.atr_med) else float(last.atr_med)))
        cur_w = (p["shares"] * close / eq) if p else 0.0

        lv = next((x for x in sorted(C.RSI_LEVELS) if last.rsi < x), None)
        if lv is not None and 1 <= int(last[f"l{lv}_days"]) <= look:
            grade = {30: 1, 20: 2, 10: 3}[lv]
            ok = p is None or (p["kind"] == "left" and not p["trail"] and p["grade"] < grade)
            if ok:
                contra = score < C.CONTRARIAN_SCORE and cats.get(c) in C.CONTRARIAN_CATS
                scale = (1.0 if above_year in (True, None) or contra else 0.5) * (0.5 if high_vol else 1.0)
                tgt = cap * cum[grade - 1] * scale
                amt = (tgt - cur_w) * eq
                if amt >= C.SIM_MIN_ORDER:
                    stop = close - C.STOP_ATR_K * atr if grade == 3 else None
                    buys.append(dict(code=c, side="buy", amount=amt, prio=grade, date=today,
                                     reason=f"左侧·RSI破{lv}（{last.rsi:.1f}），目标仓位 {tgt * 100:.0f}%",
                                     meta=dict(kind="left", grade=grade, stop=stop, title=f"左侧·RSI破{lv}")))
            continue

        if p is None and bool(last.sig_right) and last.right_days <= C.RIGHT_FRESH_DAYS:
            if (last.bias_atr > C.BIAS_HOT_ATR or last.rsi >= C.RSI_OVERBOUGHT[0]
                    or rs_rank[c] > len(rows) * C.RS_WEAK_FRAC):
                continue                                         # 过热不追
            stop = close - C.STOP_ATR_K * atr
            w = min(cap, C.RISK_PER_TRADE / ((close - stop) / close)) * (0.5 if high_vol else 1.0)
            strong = bool(last.vol_ratio >= C.VOL_RATIO_STRONG and last.dif > 0 and last.dea > 0)
            if w * eq >= C.SIM_MIN_ORDER:
                buys.append(dict(code=c, side="buy", amount=w * eq, prio=2.5 if strong else 1.5, date=today,
                                 reason=f"右侧·放量拉升{'（强）' if strong else ''}，量比 {last.vol_ratio:.2f}，"
                                        f"目标仓位 {w * 100:.0f}%",
                                 meta=dict(kind="right", grade=2 if strong else 1, stop=stop,
                                           title="右侧·放量拉升")))

    # 总仓位上限跟市场温度走（与日报的"参考总仓位上限"同一张表）
    held_mv = sum(p["shares"] * px.get(c, p["last_px"]) for c, p in st["positions"].items())
    sell_mv = sum((st["positions"][o["code"]]["shares"] if o["shares"] == "all" else o["shares"]) * px[o["code"]]
                  for o in orders)
    room = C.TEMP_CAP[label] / 100 * eq - (held_mv - sell_mv)
    # 现金不够时按优先级分配：左侧深度超卖 > 强右侧 > 普通
    budget = min(room, st["cash"] + sell_mv)
    for o in sorted(buys, key=lambda x: -x["prio"]):
        if budget < C.SIM_MIN_ORDER:
            break
        o["amount"] = round(min(o["amount"], budget), 2)
        budget -= o["amount"]
        orders.append(o)

    st["pending"] = [o for o in st["pending"] if o["code"] not in {x["code"] for x in orders}] + orders
    st["last_decide"] = today
    return orders


# ============================================================================ 驱动
def _bars_rows(frames: dict, i_of: dict | None = None):
    bars, rows = {}, {}
    for c, f in frames.items():
        i = len(f) - 1 if i_of is None else i_of.get(c)
        if i is None or i < 1:
            continue
        last, prev = f.iloc[i], f.iloc[i - 1]
        d = f.index[i].strftime("%Y-%m-%d")
        bars[c] = dict(date=d, open=float(last.open), prev_close=float(prev.close))
        rows[c] = (last, prev)
    return bars, rows


def backtest(frames: dict, names: dict, bench_code: str, years: int = C.SIM_BACKTEST_YEARS) -> dict:
    cal = frames[bench_code].index
    start = cal[-1] - pd.DateOffset(years=years)
    start = max(start, cal[min(C.MA_LONG + 10, len(cal) - 1)])   # 至少留出 200 日线的预热期
    dates = cal[cal >= start]
    st = new_state(dates[0].strftime("%Y-%m-%d"))
    pos = {c: {d: i for i, d in enumerate(f.index)} for c, f in frames.items()}
    for k, t in enumerate(dates):
        today = t.strftime("%Y-%m-%d")
        bars, rows = _bars_rows(frames, {c: pos[c].get(t) for c in frames})
        px = {c: float(r[0].close) for c, r in rows.items()}
        if k == 0:
            st["base"] = {c: v for c, v in px.items() if c in names}
            st["base"]["_bench"] = px[bench_code]
        fill(st, bars, names, today)
        mark(st, px, today, False, bench_code, {c: float(r[1].close) for c, r in rows.items()})
        decide(st, {c: r for c, r in rows.items() if c in names}, names, today)
    st["pending"] = []
    return st


def run_live(out: Path, pool: list, frames: dict, session: str, latest: str, generated: str,
             bench_code: str = C.BENCHMARK["code"], demo: bool = False) -> dict | None:
    sd = out / "sim"
    sd.mkdir(parents=True, exist_ok=True)
    sf = sd / "state.json"
    names = {p["code"]: p["name"] for p in pool}
    st = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() and not demo else None
    bars, rows = _bars_rows(frames)
    px = {c: float(r[0].close) for c, r in rows.items()}
    close = session == "close"
    if st is None:
        if not close:
            return None                                          # 第一次收盘运行才开户
        st = new_state(latest)
        st["base"] = {c: v for c, v in px.items() if c in names}
        st["base"]["_bench"] = px[bench_code]
    fill(st, bars, names, latest)
    mark(st, px, latest, not close, bench_code, {c: float(r[1].close) for c, r in rows.items()})
    if close and st["last_decide"] != latest:
        decide(st, {c: r for c, r in rows.items() if c in names}, names, latest)
    sf.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    bf = sd / "backtest.json"
    if close or demo or not bf.exists():
        bt = backtest(frames, names, bench_code)
        bf.write_text(json.dumps(bt, ensure_ascii=False), encoding="utf-8")
    else:
        bt = json.loads(bf.read_text(encoding="utf-8"))
    (out / "sim.html").write_text(render(st, bt, px, names, session, generated), encoding="utf-8")
    return summary(st)


# ============================================================================ 统计
def perf(st) -> dict:
    nav = st["nav"]
    if not nav:
        return {}
    eq = np.array([x["equity"] for x in nav])
    peak = np.maximum.accumulate(eq)
    dd = float(((eq / peak) - 1).min() * 100)
    ret = (eq[-1] / st["cash0"] - 1) * 100
    b = nav[-1]["bench"]
    ew = nav[-1]["ew"]
    m64 = [x.get("m6040") for x in nav]
    n = len(nav)
    ann = ((eq[-1] / st["cash0"]) ** (252 / max(n - 1, 1)) - 1) * 100 if n > 120 else None
    rets = np.diff(eq) / eq[:-1] if n > 2 else np.array([])
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 20 and rets.std() > 0 else None
    bd = None
    if n > 1 and all(x["bench"] for x in nav):
        bb = np.array([x["bench"] for x in nav])
        bd = float(((bb / np.maximum.accumulate(bb)) - 1).min() * 100)
    cl = st["closed"]
    wins = [x for x in cl if x["pnl"] > 0]
    loss = [x for x in cl if x["pnl"] <= 0]
    pf = (sum(x["pnl"] for x in wins) / -sum(x["pnl"] for x in loss)) if loss and sum(x["pnl"] for x in loss) < 0 else None
    return dict(equity=float(eq[-1]), ret=ret, bench=(b - 1) * 100 if b else None,
                ew=(ew - 1) * 100 if ew else None,
                m6040=((m64[-1] / m64[0] - 1) * 100) if m64[0] and m64[-1] else None, dd=dd, bench_dd=bd, ann=ann, sharpe=sharpe,
                day=float(eq[-1] - eq[-2]) if n > 1 else 0.0, pos=nav[-1]["pos"], cash=nav[-1]["cash"],
                n_closed=len(cl), win=len(wins) / len(cl) * 100 if cl else None, pf=pf,
                days=n, avg_pos=float(np.mean([x["pos"] for x in nav])))


def by_signal(closed: list) -> list:
    groups: dict = {}
    for x in closed:
        groups.setdefault(x["title"], []).append(x)
    out = []
    for t in ["左侧·RSI破30", "左侧·RSI破20", "左侧·RSI破10", "右侧·放量拉升"]:
        g = groups.get(t, [])
        if not g:
            continue
        w = [x for x in g if x["pnl"] > 0]
        l = [x for x in g if x["pnl"] <= 0]
        aw = np.mean([x["ret"] for x in w]) if w else 0
        al = np.mean([x["ret"] for x in l]) if l else 0
        out.append(dict(title=t, n=len(g), win=len(w) / len(g) * 100, avg=float(np.mean([x["ret"] for x in g])),
                        ratio=(aw / -al) if al < 0 else None, pnl=sum(x["pnl"] for x in g),
                        days=float(np.mean([x["days"] for x in g]))))
    return out


def by_exit(closed: list) -> list:
    groups: dict = {}
    for x in closed:
        k = x["reason"].split("（")[0].split("，")[0]
        groups.setdefault(k, []).append(x)
    return sorted(([k, len(v), float(np.mean([x["ret"] for x in v])), sum(x["pnl"] for x in v)]
                   for k, v in groups.items()), key=lambda x: -x[1])


def summary(st) -> dict:
    p = perf(st)
    return dict(equity=p.get("equity"), ret=p.get("ret"), bench=p.get("bench"),
                n_pos=len(st["positions"]), n_pending=len(st["pending"]))


# ============================================================================ 页面
def _pct(v, nd=1, color=True):
    if v is None:
        return '<span class="mute">—</span>'
    cls = ("up" if v > 0 else "down" if v < 0 else "") if color else ""
    return f'<span class="num {cls}">{v:+.{nd}f}%</span>'


def _money(v, sign=False):
    if v is None:
        return "—"
    return f'{v:+,.0f}' if sign else f'{v:,.0f}'


SIM_CSS = """
.tile b{font-family:var(--num);font-size:19px;white-space:nowrap}
.tile b span{font-size:inherit}
.tile span{white-space:normal}
@media (max-width:600px){.tiles{grid-template-columns:repeat(2,1fr)}}
.wrap{overflow-x:hidden}
"""


def _pnl_td(v):
    if v is None:
        return '<td class="mute">—</td>'
    return f'<td class="num {"up" if v > 0 else "down" if v < 0 else ""}">{_money(v, True)}</td>'


def _hold_total(st, eq):
    ps = st["positions"].values()
    mv = sum(q["shares"] * q["last_px"] for q in ps)
    cost = sum(q["cost"] for q in ps)
    day = sum(q.get("day_pnl") or 0 for q in ps)
    fl = sum(q.get("float_pnl") or 0 for q in ps)
    return (f'<tfoot><tr><td><b>合计</b></td><td></td><td></td><td></td>'
            f'<td class="num"><b>{_money(mv)}</b></td><td class="num">{mv / eq * 100:.0f}%</td>'
            f'{_pnl_td(day)}{_pnl_td(fl)}<td>{_pct((mv / cost - 1) * 100 if cost else None, 2)}</td>'
            f'<td></td><td></td><td></td></tr></tfoot>')


def _sh(o):
    return "全部" if o["shares"] == "all" else f'{o["shares"]:,} 股'


def chart(nav: list, w=640, h=220, label="净值曲线") -> str:
    """四条线：策略 / SPY / 60/40 股债 / 池子等权持有，都换算成累计收益率。"""
    if len(nav) < 2:
        return '<div class="empty">刚开始运行，净值曲线需要至少两个交易日才能画出来。</div>'
    s = [x["equity"] / nav[0]["equity"] * 100 - 100 for x in nav]
    b = [(x["bench"] / nav[0]["bench"] * 100 - 100) if x["bench"] and nav[0]["bench"] else None for x in nav]
    e = [(x["ew"] / nav[0]["ew"] * 100 - 100) if x["ew"] and nav[0]["ew"] else None for x in nav]
    m0 = nav[0].get("m6040")
    q = [(x["m6040"] / m0 * 100 - 100) if m0 and x.get("m6040") else None for x in nav]
    vals = [v for arr in (s, b, e, q) for v in arr if v is not None] + [0]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 52, 8, 10, 30
    n = len(nav)
    X = lambda i: L + i * (w - L - R) / (n - 1)
    Y = lambda v: T + (hi - v) / (hi - lo) * (h - T - B)

    def path(arr):
        pts, cmd = [], "M"
        for i, v in enumerate(arr):
            if v is None:
                cmd = "M"
                continue
            pts.append(f"{cmd}{X(i):.1f},{Y(v):.1f}")
            cmd = "L"
        return "".join(pts)

    step = 10 ** math.floor(math.log10(max(hi - lo, 1e-9) / 4))
    step = next(m * step for m in (1, 2, 5, 10) if (hi - lo) / (m * step) <= 5)
    ticks = [k * step for k in range(math.ceil(lo / step), math.floor(hi / step) + 1)]
    g = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{E(label)}" style="width:100%;height:auto;display:block">']
    for t in ticks:
        g.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--line)" '
                 f'stroke-width="{1.4 if t == 0 else 0.8}"/>'
                 f'<text x="{L - 5}" y="{Y(t) + 3.5:.1f}" text-anchor="end" font-size="15" fill="var(--mute)" '
                 f'font-family="var(--num)">{t:+.0f}%</text>')
    for i in sorted({0, n // 2, n - 1}):
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        g.append(f'<text x="{X(i):.1f}" y="{h - 8}" text-anchor="{anchor}" font-size="15" fill="var(--mute)" '
                 f'font-family="var(--num)">{nav[i]["date"]}</text>')
    g.append(f'<path d="{path(e)}" fill="none" stroke="var(--s3)" stroke-width="1.5"/>')
    g.append(f'<path d="{path(q)}" fill="none" stroke="var(--s2)" stroke-width="1.5"/>')
    g.append(f'<path d="{path(b)}" fill="none" stroke="var(--s1)" stroke-width="1.5"/>')
    g.append(f'<path d="{path(s)}" fill="none" stroke="var(--up)" stroke-width="2.2" stroke-linejoin="round"/>')
    g.append("</svg>")
    leg = (f'<div class="legend"><span><i style="border-color:var(--up)"></i>模拟盘 {_pct(s[-1])}</span>'
           f'<span><i style="border-color:var(--s1)"></i>标普500(SPY) {_pct(b[-1])}</span>'
           + (f'<span><i style="border-color:var(--s2)"></i>60/40 股债 {_pct(q[-1])}</span>' if q[-1] is not None else "") +
           f'<span><i style="border-color:var(--s3)"></i>池子等权持有 {_pct(e[-1])}</span></div>')
    return f'<div class="rsi">{"".join(g)}{leg}</div>'


def kpis(p: dict, cash0: float, live=True) -> str:
    ex = p["ret"] - p["bench"] if p.get("bench") is not None else None
    t = [
        ("t", _money(p["equity"]), "总资产（美元）"),
        ("r" if p["ret"] >= 0 else "l", _pct(p["ret"], 2), "累计收益"),
        ("s", _pct(ex, 2), "跑赢标普500"),
        ("l", f'<span class="num">{p["dd"]:.1f}%</span>', "最大回撤"),
    ]
    if live:
        t += [("t", f'<span class="num {"up" if p["day"] > 0 else "down" if p["day"] < 0 else ""}">{_money(p["day"], True)}</span>',
               "今日盈亏（美元）"),
              ("t", f'<span class="num">{p["pos"]:.0f}%</span>', "当前仓位"),
              ("t", _money(p["cash"]), "可用现金"),
              ("t", f'<span class="num">{p["win"]:.0f}%</span>' if p["win"] is not None else "—",
               f'胜率（{p["n_closed"]} 笔已平）')]
    else:
        t += [("t", _pct(p["ann"], 1) if p["ann"] is not None else "—", "年化收益"),
              ("t", f'<span class="num">{p["sharpe"]:.2f}</span>' if p["sharpe"] is not None else "—", "夏普比率"),
              ("t", f'<span class="num">{p["win"]:.0f}%</span>' if p["win"] is not None else "—",
               f'胜率（{p["n_closed"]} 笔）'),
              ("t", f'<span class="num">{p["pf"]:.2f}</span>' if p["pf"] else "—", "盈亏比（总盈/总亏）")]
    return '<div class="tiles">' + "".join(
        f'<div class="tile {k}"><b>{v}</b><span>{E(lab)}</span></div>' for k, v, lab in t) + "</div>"


def sig_table(st) -> str:
    rows = by_signal(st["closed"])
    if not rows:
        return '<div class="empty">还没有平仓的交易，信号成绩单会在第一笔平仓后出现。</div>'
    cells = []
    for x in rows:
        ratio = f'{x["ratio"]:.2f}' if x["ratio"] else "—"
        cells.append(f'<tr><td>{E(x["title"])}</td><td class="num">{x["n"]}</td><td class="num">{x["win"]:.0f}%</td>'
                     f'<td>{_pct(x["avg"], 2)}</td><td class="num">{ratio}</td>'
                     f'<td class="num {"up" if x["pnl"] > 0 else "down"}">{_money(x["pnl"], True)}</td>'
                     f'<td class="num">{x["days"]:.0f}</td></tr>')
    ex = by_exit(st["closed"])
    exits = "".join(f'<tr><td>{E(k)}</td><td class="num">{n}</td><td>{_pct(a, 2)}</td>'
                    f'<td class="num {"up" if s > 0 else "down"}">{_money(s, True)}</td></tr>' for k, n, a, s in ex)
    return (f'<div class="tblwrap"><table><thead><tr><th>入场信号</th><th>笔数</th><th>胜率</th><th>平均每笔</th>'
            f'<th>赚亏比</th><th>合计盈亏</th><th>平均持有天</th></tr></thead><tbody>{"".join(cells)}</tbody></table></div>'
            f'<div class="tblwrap"><table><thead><tr><th>离场原因</th><th>笔数</th><th>平均每笔</th><th>合计盈亏</th>'
            f'</tr></thead><tbody>{exits}</tbody></table></div>')


def render(st, bt, px: dict, names: dict, session: str, generated: str) -> str:
    from .report import CSS
    p = perf(st)
    pb = perf(bt)
    nav = st["nav"]
    live_days = len(nav)
    sess = {"close": "收盘", "noon": "午盘", "mid": "盘中", "tail": "尾盘"}.get(session, session)
    h = [f'<header class="head"><h1>美股 ETF 模拟盘 · 自动跟单日报信号</h1>'
         f'<div class="meta"><span class="badge {"" if session == "close" else "noon"}">{sess}</span>'
         f'<span>{st["start"]} 开户</span><span>初始资金 ${st["cash0"]:,.0f}</span>'
         f'<span>单只上限 {C.SIM_MAX_POS * 100:.0f}%</span><span>更新于 {generated[-11:]}</span>'
         f'<a href="./">← 返回日报</a></div></header>']
    if session != "close":
        h.append('<div class="banner">盘中更新：市值按盘中价计算，收盘后会再更新一次；新订单只在收盘后生成。</div>')
    if live_days < 20:
        h.append(f'<div class="banner">模拟盘刚运行 {live_days} 个交易日，样本太少，先看下方「历史回测」了解这套规则长期大概什么样。</div>')

    h.append('<nav><a href="#now">账户</a><a href="#hold">持仓</a><a href="#todo">待成交</a><a href="#trades">成交</a>'
             '<a href="#score">成绩单</a><a href="#bt">历史回测</a><a href="#rules">规则</a></nav>')

    h.append('<section id="now"><h2>账户概况 <small>与标普500、池子等权持有对比</small></h2>')
    h.append(kpis(p, st["cash0"]))
    h.append(chart(nav, label="模拟盘累计收益与标普500、池子等权持有对比"))
    h.append("</section>")

    # 持仓
    h.append(f'<section id="hold"><h2>当前持仓 <small>{len(st["positions"])} 只</small></h2>')
    if st["positions"]:
        eq = p["equity"]
        trs = []
        for c, q in sorted(st["positions"].items(), key=lambda kv: -kv[1]["shares"] * kv[1]["last_px"]):
            mv = q["shares"] * q["last_px"]
            avg = q["cost"] / q["shares"]
            kind = "left" if q["kind"] == "left" else "right"
            stop = f'{q["stop"]:.3f}' if q["stop"] else "—"
            trs.append(f'<tr><td class="sg {kind}"><a>{E(names.get(c, c))}<span class="cd">{c}</span></a></td>'
                       f'<td class="num">{q["shares"]:,}</td><td class="num">{avg:.3f}</td><td class="num">{q["last_px"]:.3f}</td>'
                       f'<td class="num">{_money(mv)}</td><td class="num">{mv / eq * 100:.0f}%</td>'
                       f'{_pnl_td(q.get("day_pnl"))}{_pnl_td(q.get("float_pnl"))}'
                       f'<td>{_pct((q["last_px"] / avg - 1) * 100, 2)}</td>'
                       f'<td class="num">{stop}</td>'
                       f'<td>{E(q["title"])}{" · 已减半" if q["took"] else ""}</td>'
                       f'<td class="num">{q["entry"][5:]}</td></tr>')
        h.append('<div class="tblwrap"><table><thead><tr><th>ETF</th><th>股数</th><th>成本价</th><th>现价</th>'
                 '<th>市值</th><th>占比</th><th>当日盈亏值</th><th>浮动盈亏值</th><th>浮动盈亏%</th><th>止损/止盈线</th><th>入场信号</th><th>建仓</th>'
                 f'</tr></thead><tbody>{"".join(trs)}</tbody>{_hold_total(st, eq)}</table></div>')
    else:
        h.append('<div class="empty">空仓。没有信号就不动，现金也是一种仓位。</div>')
    h.append("</section>")

    # 待成交
    h.append(f'<section id="todo"><h2>下一交易日开盘待成交 <small>{len(st["pending"])} 笔</small></h2>')
    if st["pending"]:
        h.append('<div class="list">' + "".join(
            f'<div class="li"><span><b class="{"up" if o["side"] == "buy" else "down"}">'
            f'{"买入" if o["side"] == "buy" else "卖出"}</b> {E(names.get(o["code"], o["code"]))}'
            f'<span class="ci">{o["code"]}</span></span>'
            f'<span class="num">{("约 $" + _money(o["amount"]) + "") if o["side"] == "buy" else _sh(o)}</span>'
            f'<span class="why">{E(o["reason"])}（{o["date"]} 收盘信号）</span></div>'
            for o in st["pending"]) + "</div>")
    else:
        h.append('<div class="empty">没有待成交的订单。</div>')
    h.append("</section>")

    # 成交
    tr = st["trades"][-40:][::-1]
    h.append(f'<section id="trades"><h2>成交记录 <small>最近 {len(tr)} 笔，共 {len(st["trades"])} 笔</small></h2>')
    if tr:
        h.append('<div class="tblwrap"><table><thead><tr><th>日期</th><th>ETF</th><th>方向</th><th>成交价</th>'
                 '<th>股数</th><th>金额</th><th>盈亏</th><th style="text-align:left">原因</th></tr></thead><tbody>' + "".join(
                     f'<tr><td class="num">{t["date"][5:]}</td><td>{E(t["name"])}<span class="cd">{t["code"]}</span></td>'
                     f'<td class="{"up" if t["side"] == "买入" else "down"}">{t["side"]}</td><td class="num">{t["px"]:.3f}</td>'
                     f'<td class="num">{t["shares"]:,}</td><td class="num">{_money(t["amount"])}</td>'
                     f'<td class="num {"" if t["pnl"] is None else "up" if t["pnl"] > 0 else "down"}">'
                     f'{"—" if t["pnl"] is None else _money(t["pnl"], True)}</td>'
                     f'<td style="text-align:left;white-space:normal;min-width:160px">{E(t["reason"])}</td></tr>'
                     for t in tr) + "</tbody></table></div>")
    else:
        h.append('<div class="empty">还没有成交。收盘出现信号后，下一交易日开盘自动成交。</div>')
    h.append("</section>")

    h.append('<section id="score"><h2>信号成绩单 <small>模拟盘已平仓交易，按入场信号分组</small></h2>')
    h.append(sig_table(st))
    h.append("</section>")

    # 回测
    h.append(f'<section id="bt"><h2>历史回测 <small>同一套规则，{bt["start"]} 至 {bt["nav"][-1]["date"]}，'
             f'初始 ${bt["cash0"]:,.0f}</small></h2>')
    h.append(f'<div class="banner">回测是“如果过去 {C.SIM_BACKTEST_YEARS} 年一直照这套规则做”的结果（覆盖 2022 年股债双杀），用于判断规则本身有没有优势，'
             f'不代表未来收益。池子是今天选出来的，存在一定的“幸存者偏差”；分红已按税后 {(1 - C.DIV_WITHHOLD) * 100:.0f}% 再投入计入。</div>')
    h.append(kpis(pb, bt["cash0"], live=False))
    # 智囊团·巴菲特之问：这套规则跑得赢"什么都不做、买 SPY 拿着"吗？用回撤调整后的收益说话
    if pb.get("bench") is not None:
        calmar = lambda r, d: r / abs(d) if d else None   # noqa: E731
        mine, spy = calmar(pb["ret"], pb["dd"]), calmar(pb["bench"], pb.get("bench_dd") or 0)
        beat_ret = pb["ret"] > pb["bench"]
        beat_risk = mine is not None and spy is not None and mine > spy
        verdict = ("收益和风险调整后都跑赢 SPY，规则有优势。" if beat_ret and beat_risk else
                   "收益没跑赢 SPY，但回撤小得多、风险调整后更好，适合想少坐过山车的人。" if beat_risk else
                   "收益跑赢 SPY，但承担的回撤更大，风险调整后并不划算。" if beat_ret else
                   "收益和风险调整后都没跑赢 SPY：如果真实数据也是这样，长期定投 SPY 更省心，这份日报更适合当买点提示器而不是交易系统。")
        h.append(f'<div class="banner"><b>和“买入 SPY 拿着不动”比：</b>{verdict}'
                 f'（策略 {pb["ret"]:+.1f}% / 最大回撤 {pb["dd"]:.1f}%；SPY {pb["bench"]:+.1f}% / 最大回撤 '
                 f'{(pb.get("bench_dd") or 0):.1f}%'
                 + (f'；60/40 股债 {pb["m6040"]:+.1f}%' if pb.get("m6040") is not None else "") + '）</div>')
    h.append(chart(bt["nav"], label="历史回测累计收益与标普500、池子等权持有对比"))
    dd_b = f'，同期标普500最大回撤 {pb["bench_dd"]:.1f}%' if pb.get("bench_dd") is not None else ""
    h.append(f'<div class="sub"><div>回测期平均仓位 {pb["avg_pos"]:.0f}%，共平仓 {pb["n_closed"]} 笔{dd_b}。</div></div>')
    h.append(sig_table(bt))
    h.append("</section>")

    cums = {g: tranche_cum(g) for g in C.LEFT_TRANCHES}
    rules = [
        f"只在收盘后那次运行（美东 16:30 左右，北京时间早上）按日报信号下单，订单在下一交易日开盘价成交；"
        f"滑点按档位 {'/'.join(f'{v * 100:.2f}%' for v in C.SIM_SLIP.values())}（一/二/三档），零佣金，卖出另计监管费约 {C.SIM_SELL_FEE * 1e4:.1f}‱。"
        "美股没有涨跌停，开盘跳空就按开盘价成交。",
        "左侧低吸：RSI14 跌破 30 / 20 / 10 依次加仓到单只上限的 "
        + "；".join(f"{C.GROUP_CN[g]}品种 {'/'.join(f'{x * 100:.0f}%' for x in v)}" for g, v in cums.items())
        + f"。单只上限 {C.SIM_MAX_POS * 100:.0f}%，高波动品种（hv 标记）{C.SIM_MAX_POS_HV * 100:.0f}%；200 日线下方减半，当前高波动再减半。只在当天新跌破那一档时买。",
        f"左侧离场：反抽到 MA20 先卖一半，剩下的保本 + 吊灯止盈线跟踪；{C.FWD_DAYS} 个交易日仍站不回 MA5 认错清仓；"
        f"三档打满后再跌 {C.STOP_ATR_K:.0f}×ATR 止损。",
        f"右侧跟随：MA3/5/7 同步向上 + 放量，启动 {C.RIGHT_FRESH_DAYS} 天内、乖离不超过 {C.BIAS_HOT_ATR:.0f} 倍 ATR、RSI<70 才买；"
        f"仓位按“跌到止损价（收盘价 − {C.STOP_ATR_K:.0f}×ATR）最多亏总资产 {C.RISK_PER_TRADE * 100:.0f}%”计算；止损价随吊灯止盈线只上移不下移，跌破即清仓。",
        "高抛：RSI ≥ 80、涨后三线拐头、高位死叉，各触发一次就卖一半；跌破吊灯止盈线清仓；RSI ≥ 70 时把止损收紧到吊灯止盈线。",
        f"减半后剩余不到总资产 {C.SIM_DUST * 100:.0f}% 的直接清掉；总仓位不超过市场温度对应的上限（"
        + "、".join(f"{k}{v}%" for k, v in C.TEMP_CAP.items()) + "）；额度不够时深度超卖与强右侧优先。不加杠杆、不做空、不用碎股。",
        f"价格用税后复权价：拆股已调整，分红按扣 {C.DIV_WITHHOLD * 100:.0f}% 预扣税后再投入计算，贴近中国投资者的真实到手收益。现金不计利息。",
    ]
    h.append('<section id="rules"><h2>交易规则 <small>改参数在 config.py 的「模拟盘」一节</small></h2>'
             '<details open><summary>模拟盘怎么下单</summary><ol>' + "".join(f"<li>{E(x)}</li>" for x in rules) +
             '</ol></details><div class="foot">模拟盘只用来检验规则，不构成投资建议。</div></section>')

    return ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>美股 ETF 模拟盘</title><style>{CSS}{SIM_CSS}</style></head><body><div class="wrap">'
            + "\n".join(h) + "</div></body></html>")
