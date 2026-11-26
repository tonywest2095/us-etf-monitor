"""池子体检（ETF 层面的优胜劣汰）：python -m us_etf_monitor.pool_audit [--out docs]

对池内每只 ETF 及其同赛道候选（config.POOL 的 alts）拉取：规模、近 3 个月日均成交额、买卖价差、费率、前五大持仓。
- 低于流动性门槛（MIN_AUM / MIN_DOLLAR_VOL / MAX_SPREAD）的标红；
- 候选的规模和成交额都超过现任 SWAP_RATIO 倍时，建议替换（连续两个月都这样再动手，避免来回换）；
- 前五大持仓列出来，人工确认"持仓与名称相符"。
结果写到 docs/pool.html 和 docs/pool_audit.json。workflow 每月第一个交易日自动跑一次。
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from html import escape as E
from pathlib import Path

from . import config as C


def snapshot(code: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(code)
    info = {}
    try:
        info = t.info or {}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] {code} info: {e}")
    px = info.get("regularMarketPrice") or info.get("previousClose") or info.get("navPrice")
    adv = info.get("averageDailyVolume3Month") or info.get("averageVolume")
    bid, ask = info.get("bid"), info.get("ask")
    spread = (ask - bid) / ((ask + bid) / 2) if bid and ask and ask > bid > 0 else None
    top = []
    try:
        th = t.funds_data.top_holdings
        top = [f"{i} {w * 100:.1f}%" for i, w in th["Holding Percent"].head(5).items()]
    except Exception:  # noqa: BLE001
        pass
    er = info.get("netExpenseRatio") or info.get("annualReportExpenseRatio")
    return dict(code=code, name=info.get("longName") or info.get("shortName") or code,
                aum=info.get("totalAssets"), dollar_vol=(adv * px) if adv and px else None,
                spread=spread, expense=er, top=top)


def grade(s: dict) -> list[str]:
    bad = []
    if s["aum"] is not None and s["aum"] < C.MIN_AUM:
        bad.append(f"规模 {s['aum'] / 1e9:.1f}B < {C.MIN_AUM / 1e9:.0f}B")
    if s["dollar_vol"] is not None and s["dollar_vol"] < C.MIN_DOLLAR_VOL:
        bad.append(f"日均成交 {s['dollar_vol'] / 1e6:.0f}M < {C.MIN_DOLLAR_VOL / 1e6:.0f}M")
    if s["spread"] is not None and s["spread"] > C.MAX_SPREAD:
        bad.append(f"价差 {s['spread'] * 100:.2f}% > {C.MAX_SPREAD * 100:.2f}%")
    return bad


def better(alt: dict, cur: dict) -> bool:
    try:
        return (alt["aum"] > cur["aum"] * C.SWAP_RATIO and alt["dollar_vol"] > cur["dollar_vol"] * C.SWAP_RATIO)
    except TypeError:
        return False


def _fmt(v, unit=1e9, suf="B"):
    return "—" if v is None else f"{v / unit:,.1f}{suf}"


def run(out: Path):
    rows = []
    for p in C.POOL:
        cur = snapshot(p["code"])
        time.sleep(0.5)
        alts = []
        for a in p["alts"]:
            s = snapshot(a)
            s["better"] = better(s, cur)
            alts.append(s)
            time.sleep(0.5)
        rows.append(dict(p=p, cur=cur, bad=grade(cur), alts=alts))
        flag = "⚠ " + "；".join(grade(cur)) if grade(cur) else "OK"
        swap = [a["code"] for a in alts if a["better"]]
        print(f"{p['code']:5} {p['name']:10} 规模 {_fmt(cur['aum'])} 日成交 {_fmt(cur['dollar_vol'], 1e6, 'M')} "
              f"{flag}" + (f"  → 建议考虑换成 {'/'.join(swap)}" if swap else ""))

    out.mkdir(parents=True, exist_ok=True)
    prev_file = out / "pool_audit.json"
    prev = json.loads(prev_file.read_text(encoding="utf-8")) if prev_file.exists() else {}
    now = datetime.now().strftime("%Y-%m-%d")
    cur_swaps = {r["p"]["code"]: [a["code"] for a in r["alts"] if a["better"]] for r in rows}
    prev_file.write_text(json.dumps(dict(date=now, swaps=cur_swaps), ensure_ascii=False), encoding="utf-8")

    trs = []
    for r in rows:
        p, cur = r["p"], r["cur"]
        twice = [c for c in cur_swaps[p["code"]] if c in (prev.get("swaps") or {}).get(p["code"], [])]
        verdict = ("连续两个月候选更好，建议换成 " + "/".join(twice) if twice else
                   "候选更好，下月再确认" if cur_swaps[p["code"]] else
                   "；".join(r["bad"]) if r["bad"] else "保留")
        alts = "<br>".join(f'{a["code"]}：规模 {_fmt(a["aum"])}，日成交 {_fmt(a["dollar_vol"], 1e6, "M")}'
                           for a in r["alts"]) or "—"
        trs.append(f'<tr><td><b>{p["code"]}</b><br><span class="m">{E(p["name"])}</span></td>'
                   f'<td>{_fmt(cur["aum"])}</td><td>{_fmt(cur["dollar_vol"], 1e6, "M")}</td>'
                   f'<td>{"—" if cur["spread"] is None else f"{cur["spread"] * 100:.3f}%"}</td>'
                   f'<td>{"—" if cur["expense"] is None else f"{cur["expense"]:.2f}%"}</td>'
                   f'<td class="m">{E("、".join(cur["top"])) or "—"}</td><td class="m">{alts}</td>'
                   f'<td class="{"bad" if r["bad"] or twice else ""}">{E(verdict)}</td></tr>')
    html = ('<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>美股 ETF 池子体检</title><style>body{font:14px/1.6 -apple-system,"PingFang SC",sans-serif;padding:12px;margin:0}'
            'table{border-collapse:collapse;font-size:12.5px}td,th{border-bottom:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}'
            '.m{color:#666;font-size:12px}.bad{color:#b00;font-weight:600}.w{overflow-x:auto}</style>'
            f'<h1>美股 ETF 池子体检</h1><p class="m">{now} 生成。门槛：规模 ≥ {C.MIN_AUM / 1e9:.0f}B 美元，'
            f'日均成交 ≥ {C.MIN_DOLLAR_VOL / 1e6:.0f}M 美元，价差 ≤ {C.MAX_SPREAD * 100:.2f}%。'
            f'候选的规模和成交额都超过现任 {C.SWAP_RATIO} 倍、且连续两个月如此，才建议换。前五大持仓用来人工核对“持仓与名称相符”。'
            '<a href="./">← 返回日报</a></p><div class="w"><table><tr><th>ETF</th><th>规模</th><th>日均成交</th><th>价差</th>'
            '<th>费率</th><th>前五大持仓</th><th>同赛道候选</th><th>结论</th></tr>' + "".join(trs) + "</table></div>")
    (out / "pool.html").write_text(html, encoding="utf-8")
    print(f"[ok] 写入 {out / 'pool.html'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs")
    run(Path(ap.parse_args().out))
