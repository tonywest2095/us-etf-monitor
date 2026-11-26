"""入口：python -m us_etf_monitor [--size 30] [--session auto|mid|close] [--out docs] [--demo] [--force]

时段判断（美东时间，夏令时自动处理）：
- 盘中 mid  ：10:15–12:30，开盘后约 1 小时的快照（北京时间 22:30 / 23:30）
- 收盘 close：收盘后 5 分钟起（半天市 13:00 收盘也能识别），以及次日开盘前补跑
GitHub 的定时任务只认 UTC，workflow 把冬令时、夏令时两套时间都排上，
不在时段内的那次直接跳过；同一天同一时段已经出过报告的也跳过（--force 可强制）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import config as C
from . import data, events, indicators, report, signals, sim


def _js(o):
    return o.item() if hasattr(o, "item") else str(o)


def notify(text: str):
    """可选推送：设置环境变量 FEISHU_WEBHOOK（飞书群自定义机器人地址）即生效。"""
    hook = os.environ.get("FEISHU_WEBHOOK")
    if not hook:
        return
    try:
        import requests
        r = requests.post(hook, json={"msg_type": "text", "content": {"text": text}}, timeout=10)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        code = body.get("code", body.get("StatusCode", 0))
        if r.status_code != 200 or code not in (0, None):
            # 飞书出错时 HTTP 仍是 200，要看返回的 code：19021 = 签名校验失败，19024 = 关键词不匹配
            print(f"[warn] 飞书推送失败: HTTP {r.status_code}, code={code}, msg={body.get('msg')}")
        else:
            print("[info] 飞书推送成功")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 飞书推送失败: {type(e).__name__}")   # 不打印异常全文，避免带出 webhook 地址


def write_archive_index(arch: Path):
    files = sorted((p.name for p in arch.glob("*.html") if p.name != "index.html"), reverse=True)
    items = "".join(f'<li><a href="{f}">{f[:-5]}</a></li>' for f in files)
    (arch / "index.html").write_text(
        '<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>历史报告</title>'
        f'<body style="font:15px/1.8 sans-serif;padding:16px"><h1>历史报告</h1><ul>{items}</ul></body></html>',
        encoding="utf-8")


def pick_session(now, forced: str) -> tuple[str | None, str]:
    """返回 (session, 说明)。session=None 表示这次不该跑。"""
    if forced != "auto":
        return forced, "手动指定"
    today = now.date()
    hm = now.hour * 60 + now.minute
    if not data.is_session(today):
        return "close", "今天休市，按最近一个交易日收盘出报告（已出过则跳过）"
    lo, hi = C.SESSION_WINDOWS["mid"]
    close_m = data.close_minute(today)
    if hm >= close_m + C.SESSION_WINDOWS["close_after"]:
        return "close", "收盘后"
    if hm < 9 * 60 + 30:
        return "close", "开盘前，补出上一交易日收盘报告（已出过则跳过）"
    if lo <= hm <= min(hi, close_m - 30):
        return "mid", "盘中"
    return None, f"美东 {now:%H:%M} 不在运行时段（盘中 10:15–12:30，收盘后）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="美股 ETF 低吸高抛日报")
    ap.add_argument("--size", type=int, default=C.DEFAULT_TIER_SIZE, choices=[10, 20, 30])
    ap.add_argument("--session", default="auto", choices=["auto", "mid", "close"])
    ap.add_argument("--out", default="docs")
    ap.add_argument("--demo", action="store_true", help="用模拟行情生成演示报告（不联网）")
    ap.add_argument("--force", action="store_true", help="不在时段内、或已出过报告也照常生成")
    a = ap.parse_args(argv)

    now = data.now_ny()
    out = Path(a.out)
    session, why = ("close", "演示") if a.demo and a.session == "auto" else pick_session(now, a.session)
    if session is None:
        if not a.force:
            print(f"[skip] {why}")
            return 0
        session = "close"
    print(f"[info] 美东 {now:%Y-%m-%d %H:%M}，时段 {session}（{why}）")

    # 先判断这一时段是否已经出过报告，出过就不取数，省数据源额度
    today = now.date()
    if not a.demo and not a.force:
        after_close = now.hour * 60 + now.minute >= data.close_minute(today)
        expect = today if session == "mid" else data.last_session(today, after_close)
        if (out / "archive" / f"{expect}-{session}.html").exists():
            print(f"[skip] {expect} {session} 报告已生成过")
            return 0

    pool = C.pool_for(a.size)
    codes = [p["code"] for p in pool]
    extra = [c for c in (C.BENCHMARK["code"], C.SIM_BENCH_6040[0], C.SIM_BENCH_6040[1], C.VIX_CODE) if c not in codes]
    need = codes + list(dict.fromkeys(extra))

    if a.demo:
        raw = {c: data.demo_history(c, i) for i, c in enumerate(need)}
        sources, problems = {c: "demo" for c in raw}, []
    else:
        want = today if data.is_session(today) and (session == "mid" or
                                                    now.hour * 60 + now.minute >= data.close_minute(today)) else None
        raw, sources, problems = data.fetch_all(need, out / "cache", want)

    bench_code = C.BENCHMARK["code"]
    if bench_code not in raw:
        print("[fatal] 基准 SPY 行情取不到，不生成报告（保留上一期）")
        return 2
    latest = raw[bench_code].index[-1].date()
    if not a.demo:
        if session == "mid" and latest != today:
            print(f"[skip] 盘中时段但行情还停在 {latest}，数据源没有今天的盘中数据")
            return 0
        if session == "close" and data.is_session(today) and latest != today \
                and now.hour * 60 + now.minute >= data.close_minute(today):
            print(f"[skip] 收盘后行情还停在 {latest}，等下一次定时任务再试")
            return 0
    arch = out / "archive"
    if not a.force and not a.demo and (arch / f"{latest}-{session}.html").exists():
        print(f"[skip] {latest} {session} 报告已生成过")
        return 0

    got = [c for c in codes if c in raw]
    if len(got) < max(3, len(codes) // 2):
        print("[fatal] 超过一半标的取数失败，不生成报告（保留上一期）")
        return 2
    lag = [c for c in got if raw[c].index[-1].date() != latest]
    if lag:
        problems.append("以下标的行情未更新到最新交易日：" + "、".join(lag))
    hit = [c for c in got if sources[c] == "cache"]
    if hit:
        problems.append(f"{'、'.join(hit)} 使用了过期的本地缓存")
    alt = [c for c in got if sources[c] in ("tiingo", "stooq")]
    if alt:
        problems.append(f"{'、'.join(alt)} 来自备用数据源（分红按全额复权，与主源口径略有差异）")

    hm = now.hour * 60 + now.minute
    share = 1.0 if session == "close" else (C.vol_share(11 * 60) if a.demo else C.vol_share(hm))
    frames = {c: indicators.enrich(raw[c], 1 / share) for c in raw if len(raw[c]) >= 30 and c != C.VIX_CODE}
    vix = raw.get(C.VIX_CODE)

    state_file = out / "state.json"
    prev = None
    if state_file.exists() and not a.demo:
        try:
            prev = json.loads(state_file.read_text(encoding="utf-8")).get("signals")
        except Exception:  # noqa: BLE001
            prev = None

    nxt = data.next_sessions(latest, 3)
    soon = events.macro_soon(latest, nxt, 2)
    res = signals.build(pool, {c: frames[c] for c in got if c in frames}, sources, frames.get(bench_code),
                        prev, vix, soon)
    gen_bj = now.astimezone(data.BJ)
    nxt_open = data.session_open_bj(nxt[0]) if nxt else ""
    info = dict(session=session, date=str(latest), generated=now.strftime("%Y-%m-%d %H:%M"),
                generated_bj=gen_bj.strftime("%Y-%m-%d %H:%M"), next_open_bj=nxt_open, demo=a.demo, problems=problems,
                events=events.upcoming(latest, 10, set(codes)), macro_soon=soon)
    html = report.render(res, info)

    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    arch.mkdir(exist_ok=True)
    (arch / f"{latest}-{session}.html").write_text(html, encoding="utf-8")
    write_archive_index(arch)
    slim = [{k: v for k, v in r.items() if k != "spark"} for r in res["rows"]]
    info_js = {**info, "events": [{**e, "date": str(e["date"])} for e in info["events"]]}
    (out / "latest.json").write_text(
        json.dumps(dict(info=info_js, temp=res["temp"], rows=slim), ensure_ascii=False, indent=1, default=_js),
        encoding="utf-8")
    if not a.demo:
        state_file.write_text(json.dumps(dict(date=str(latest), session=session, signals=res["state"]),
                                         ensure_ascii=False), encoding="utf-8")

    summary = report.text_summary(res, info, os.environ.get("REPORT_URL", ""))
    try:
        sm = sim.run_live(out, pool, frames, session, str(latest), info["generated"], bench_code,
                          demo=a.demo)
        if sm and sm["equity"] is not None:
            summary += (f"\n模拟盘：总资产 ${sm['equity']:,.0f}（{sm['ret']:+.2f}%，SPY "
                        f"{(sm['bench'] or 0):+.2f}%），持仓 {sm['n_pos']} 只，待成交 {sm['n_pending']} 笔")
    except Exception as e:  # noqa: BLE001  模拟盘出错不影响日报
        print(f"[warn] 模拟盘运行失败: {e}")
        if a.demo:
            raise
    print(summary)
    if not a.demo:
        notify(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
