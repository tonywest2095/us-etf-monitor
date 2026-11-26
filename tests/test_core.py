"""运行：python -m pytest -q   （不联网）"""
import numpy as np
import pandas as pd

from us_etf_monitor import data, indicators as ind, signals, config as C


def _loop_sma(x, n):          # 通达信 SMA(X,N,1) 的逐日递推写法，作为独立参照
    y, out = None, []
    for v in x:
        if np.isnan(v):
            out.append(np.nan); continue
        y = v if y is None else (v + (n - 1) * y) / n
        out.append(y)
    return np.array(out)


def test_rsi_matches_tdx_formula():
    rng = np.random.default_rng(1)
    c = pd.Series(10 * np.exp(np.cumsum(rng.normal(0, 0.02, 400))))
    d = c.diff().to_numpy()
    up, ab = _loop_sma(np.clip(d, 0, None), 14), _loop_sma(np.abs(d), 14)
    ref = up / ab * 100
    got = ind.rsi(c, 14).to_numpy()
    assert np.allclose(got[60:], ref[60:], atol=1e-6)
    assert ind.rsi(pd.Series(np.arange(1, 60.0)), 14).iloc[-1] == 100


def test_macd_matches_loop():
    rng = np.random.default_rng(2)
    c = pd.Series(5 * np.exp(np.cumsum(rng.normal(0, 0.015, 300))))
    def ema(x, n):
        y, out = x[0], []
        for v in x:
            y = (2 * v + (n - 1) * y) / (n + 1); out.append(y)
        return np.array(out)
    dif = ema(c.to_numpy(), 12) - ema(c.to_numpy(), 26)
    dea = ema(dif, 9)
    a, b, h = ind.macd(c)
    assert np.allclose(a, dif) and np.allclose(b, dea) and np.allclose(h, 2 * (dif - dea))


def test_parsers():
    idx = pd.to_datetime(["2026-11-23", "2026-11-24"])
    yf = pd.DataFrame({"Open": [100, 101], "High": [102, 103], "Low": [99, 100], "Close": [101, 102],
                       "Adj Close": [100, 101.5], "Volume": [1e6, 2e6], "Dividends": [0, 0.5]}, index=idx)
    df = data.parse_yf_frame(yf)
    assert df["close"].tolist() == [101, 102] and df["div"].tolist() == [0, 0.5]
    tg = [{"date": "2026-11-23T00:00:00.000Z", "adjOpen": 1, "adjHigh": 2, "adjLow": 0.5, "adjClose": 1.5,
           "adjVolume": 10}, {"date": "2026-11-24T00:00:00.000Z", "adjOpen": 1.5, "adjHigh": 2, "adjLow": 1,
                              "adjClose": 1.8, "adjVolume": 12}]
    assert data.parse_tiingo(tg)["close"].tolist() == [1.5, 1.8]
    sq = "Date,Open,High,Low,Close,Volume\n2026-11-23,1,2,0.5,1.5,10\n2026-11-24,1.5,2,1,1.8,12\n"
    assert data.parse_stooq(sq)["close"].tolist() == [1.5, 1.8]
    assert data.parse_stooq("Exceeded the daily hits limit").empty


def test_after_tax_adjustment():
    idx = pd.bdate_range("2026-01-01", periods=4)
    raw = pd.DataFrame(dict(open=[100.0] * 4, high=[100.0] * 4, low=[100.0] * 4, close=[100, 100, 98, 98.0],
                            volume=[10] * 4, div=[0, 0, 2.0, 0]), index=idx)
    full = data.adjust(raw, 0.0)
    assert np.allclose(full["close"], [98, 98, 98, 98])          # 全额复权：除息不算跌
    net = data.adjust(raw, 0.10)
    f = 1 - 1.8 / 100                                               # 只有 90% 分红再投入
    assert np.allclose(net["close"], [100 * f, 100 * f, 98, 98])
    assert net["amount"].iloc[0] == 1000                            # 成交额用原始价


def test_signals_on_constructed_shapes():
    base = data.demo_history("XLK", 5)
    # 连续急跌 -> 必须出左侧信号
    crash = base.copy()
    f = np.cumprod(np.r_[np.ones(len(crash) - 10), np.full(10, 0.975)])
    for c in ["open", "high", "low", "close"]:
        crash[c] *= f
    r = signals.analyze(dict(code="x", name="x", cat="行业", flags=[], tier=1, index="i", recon="r"), ind.enrich(crash), "demo")
    assert r["rsi"] < 30 and r["buy"] and r["buy"][0]["kind"] == "left"
    assert r["dd_60"] < -15 and r["dd_ath"] <= r["dd_60"] + 1e-9
    # 回撤口径：距历史高点一定不小于距 60 日高点的跌幅
    e = ind.enrich(base)
    assert (e["dd_ath"] <= e["dd_60"] + 1e-9).iloc[60:].all()


def test_intraday_volume_scaling():
    base = data.demo_history("XLK", 5)
    full = ind.enrich(base)["vol_ratio"].iloc[-1]
    share = C.vol_share(10 * 60 + 30)
    part = base.copy(); part.iloc[-1, part.columns.get_loc("volume")] *= share
    mid = ind.enrich(part, 1 / share)["vol_ratio"].iloc[-1]
    assert abs(full - mid) < 1e-9


def test_pool_tiers():
    assert len(C.pool_for(10)) == 10 and len(C.pool_for(20)) == 20 and len(C.pool_for(30)) == 30
    codes = [p["code"] for p in C.POOL]
    assert len(set(codes)) == len(codes) and len(codes) <= 30
    for p in C.POOL:
        assert p["cat"] in C.CAT_ORDER and p["index"] and p["recon"]
        assert not set(p["alts"]) & set(codes)                  # 候选不能和池内重复


def test_vol_share_monotonic():
    xs = [C.vol_share(h * 60 + m) for h, m in [(9, 45), (10, 30), (12, 0), (14, 0), (15, 30), (15, 59), (16, 0)]]
    assert xs == sorted(xs) and xs[-1] == 1.0 and 0.15 < xs[1] < 0.25


def test_vol_groups_and_tranches():
    assert signals.vol_group(0.8) == "low" and signals.vol_group(1.8) == "mid" and signals.vol_group(3.5) == "high"
    for g, t in C.LEFT_TRANCHES.items():
        assert abs(sum(t) - 1) < 1e-9
    assert C.LEFT_TRANCHES["low"][0] > C.LEFT_TRANCHES["high"][0]


def test_session_picking_handles_dst_and_half_days():
    from datetime import datetime
    from us_etf_monitor.__main__ import pick_session
    ny = data.NY
    assert pick_session(datetime(2026, 11, 25, 10, 30, tzinfo=ny), "auto")[0] == "mid"
    assert pick_session(datetime(2026, 11, 25, 15, 30, tzinfo=ny), "auto")[0] is None
    assert pick_session(datetime(2026, 11, 25, 16, 30, tzinfo=ny), "auto")[0] == "close"
    assert pick_session(datetime(2026, 11, 27, 13, 30, tzinfo=ny), "auto")[0] == "close"   # 感恩节次日半天市
    assert pick_session(datetime(2026, 11, 26, 16, 30, tzinfo=ny), "auto")[0] == "close"   # 感恩节休市
    assert data.close_minute(datetime(2026, 11, 27).date()) == 13 * 60
    # GitHub 的 UTC 定时：冬令时 21:30 UTC = 16:30 ET；夏令时 20:30 UTC = 16:30 ET
    from zoneinfo import ZoneInfo
    utc = ZoneInfo("UTC")
    assert datetime(2026, 12, 1, 21, 30, tzinfo=utc).astimezone(ny).hour == 16
    assert datetime(2027, 6, 1, 20, 30, tzinfo=utc).astimezone(ny).hour == 16


def test_events():
    from datetime import date
    from us_etf_monitor import events
    assert events.third_friday(2026, 12) == date(2026, 12, 18)
    ev = events.upcoming(date(2026, 12, 1), 20, {"IWM", "SPY", "QQQ"})
    titles = [e["title"] for e in ev]
    assert any("非农" in t for t in titles) and any("FOMC" in t for t in titles)
    assert any("罗素" in t for t in titles) and any("纳指" in t for t in titles)
    soon = events.macro_soon(date(2026, 12, 8), [date(2026, 12, 9), date(2026, 12, 10)])
    assert len(soon) == 2


def _rows_frames(n=9):
    pool = C.pool_for(10)[:n]
    frames = {p["code"]: ind.enrich(data.demo_history(p["code"], i)) for i, p in enumerate(pool)}
    return pool, frames


def test_report_renders_with_required_sections():
    from us_etf_monitor import report
    pool, frames = _rows_frames()
    res = signals.build(pool, frames, {c: "demo" for c in frames}, frames["SPY"], None,
                        ind.enrich(data.demo_history("^VIX", 0)), ["12-09 FOMC 利率决议"])
    info = dict(session="close", date="2026-11-24", generated="2026-11-24 16:30", generated_bj="2026-11-25 05:30",
                next_open_bj="11-25 周三 22:30", demo=True, problems=[], events=[], macro_soon=["x"])
    html = report.render(res, info)
    for k in ["RSI14", "MA3", "MACD", "回撤", "均线图形", "术语解释", "乖离", "量比", "ATR", "RS（相对强弱）",
              "今晚操作", "成分调整", "VIX"]:
        assert k in html, k
    for p in pool:                                               # 每个 ETF 名称都带代码
        assert p["code"] in html
    for r in res["rows"]:
        for s in r["buy"]:
            if s["kind"] == "right":
                assert "大事件前减半" in s["cuts"]


def test_weak_rs_right_side_is_filtered():
    pool, frames = _rows_frames()
    res = signals.build(pool, frames, {c: "demo" for c in frames}, frames["SPY"], None)
    n = len(res["rows"])
    for r in res["rows"]:
        if any(s["kind"] == "right" for s in r["buy"]):
            assert r["rs_rank"] <= n * C.RS_WEAK_FRAC


def test_live_path_end_to_end_with_mocked_network(tmp_path, monkeypatch):
    """非演示路径：抓数 -> 缓存 -> 增量 -> 报告 -> 模拟盘 -> 同时段去重。网络层用假数据替换。"""
    from datetime import datetime
    from us_etf_monitor import __main__ as M

    def fake_raw(code, end):
        rng = np.random.default_rng(abs(hash(code)) % 2**32)
        idx = pd.bdate_range(end=end, periods=400)
        c = 50 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(idx))))
        return pd.DataFrame(dict(open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1e6, div=0.0), index=idx)

    calls = []

    def fake_batch(codes, start):
        calls.append((len(codes), start))
        return {c: fake_raw(c, "2026-11-24") for c in codes}

    monkeypatch.setattr(data, "fetch_yf_batch", fake_batch)
    monkeypatch.setattr(data, "now_ny", lambda: datetime(2026, 11, 24, 16, 40, tzinfo=data.NY))
    assert M.main(["--out", str(tmp_path), "--size", "10"]) == 0
    assert (tmp_path / "index.html").exists() and (tmp_path / "sim.html").exists()
    assert (tmp_path / "archive" / "2026-11-24-close.html").exists()
    assert (tmp_path / "cache" / "SPY.csv").exists() and (tmp_path / "cache" / "_VIX.csv").exists()
    assert calls[0][1] == C.HISTORY_START
    assert M.main(["--out", str(tmp_path), "--size", "10"]) == 0          # 同一时段第二次：跳过
    assert calls[-1][1] != C.HISTORY_START                                # 有缓存后只拉增量
    st = (tmp_path / "sim" / "state.json").read_text()
    assert '"last_decide": "2026-11-24"' in st
