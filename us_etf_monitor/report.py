"""生成自包含的单页 HTML 报告（手机优先，无外部依赖，国内网络可直接打开）。

配色按国内习惯：红涨绿跌。"""
from __future__ import annotations

from html import escape as E

from . import config as C
from .data import SOURCE_CN

CSS = """
:root{
  /* 版式：手机单列，摘要在前、明细在后；红涨绿跌；左侧=蓝、右侧=红、高抛=琥珀 */
  --bg:#f3f4f7; --card:#ffffff; --ink:#141a26; --mute:#5d6676; --line:#e1e4ea; --soft:#eef0f4;
  --up:#c62f2f; --down:#12805c; --left:#2a63c9; --warn:#b26a00; --accent:#1d3a8a;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --font:-apple-system,BlinkMacSystemFont,"PingFang SC","HarmonyOS Sans SC","Microsoft YaHei","Noto Sans SC",sans-serif;
  --num:"SF Mono","DIN Alternate","Roboto Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --bg:#10131a; --card:#191d27; --ink:#eceef3; --mute:#9aa3b2; --line:#2a303d; --soft:#222836;
    --up:#ff6b6b; --down:#3ecf9b; --left:#6ea0ff; --warn:#f0a93b; --accent:#9db7ff;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --bg:#10131a; --card:#191d27; --ink:#eceef3; --mute:#9aa3b2; --line:#2a303d; --soft:#222836;
  --up:#ff6b6b; --down:#3ecf9b; --left:#6ea0ff; --warn:#f0a93b; --accent:#9db7ff;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--font)}
.wrap{max-width:1080px;margin:0 auto;padding:16px 16px 48px;display:flex;flex-direction:column;gap:20px}
h1{font-size:22px;line-height:1.25;margin:0;text-wrap:balance}
h2{font-size:17px;margin:0;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
h2 small{font-size:12.5px;font-weight:400;color:var(--mute)}
.num{font-family:var(--num);font-variant-numeric:tabular-nums}
.mute{color:var(--mute)} .up{color:var(--up)} .down{color:var(--down)}
.head{display:flex;flex-direction:column;gap:6px}
.head .meta{font-size:12.5px;color:var(--mute);display:flex;gap:6px 12px;flex-wrap:wrap;align-items:center}
.badge{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:4px;background:var(--accent);color:var(--card)}
.badge.noon{background:var(--warn)}
.banner{border-left:3px solid var(--warn);background:var(--card);padding:10px 12px;font-size:13.5px;border-radius:0 6px 6px 0}
.lead{font-size:15.5px;font-weight:600;line-height:1.55;margin:0}
.sub{font-size:13px;color:var(--mute);display:flex;flex-direction:column;gap:2px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(64px,1fr));gap:6px}
.tile{background:var(--card);border-radius:8px;padding:8px 10px;border-top:3px solid var(--line);text-decoration:none;color:inherit;display:block;min-width:0}
.tile b{display:block;font-size:20px;line-height:1.2}
.tile span{font-size:12px;color:var(--mute);white-space:nowrap}
.tile.l{border-color:var(--left)} .tile.r{border-color:var(--up)} .tile.s{border-color:var(--warn)} .tile.t{border-color:var(--accent)}
nav{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;display:flex;gap:6px;overflow-x:auto;margin:-8px 0}
nav a,.sort button{flex:none;font:inherit;font-size:13px;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 12px;text-decoration:none;cursor:pointer}
nav a:focus-visible,.sort button:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sort button[aria-pressed="true"]{background:var(--ink);color:var(--card);border-color:var(--ink)}
section{display:flex;flex-direction:column;gap:10px;scroll-margin-top:52px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:10px}
.opp{background:var(--card);border-radius:8px;padding:12px 14px;border-left:4px solid var(--line);display:flex;flex-direction:column;gap:8px}
.opp.left{border-color:var(--left)} .opp.right{border-color:var(--up)} .opp.sell{border-color:var(--warn)}
.opp .top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.opp .nm{font-weight:700;font-size:16px}
.opp .nm small{font-weight:400;font-size:12px;color:var(--mute);margin-left:4px}
.opp ul{margin:6px 0 0;padding-left:18px;font-size:13px}
.opp .key{font-size:13.5px}
.opp details{background:none;padding:0;font-size:13px}
.opp summary{font-weight:400;color:var(--accent);font-size:13px}
.list{background:var(--card);border-radius:8px;padding:2px 14px}
.list .li{display:grid;grid-template-columns:1fr auto;gap:2px 8px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.list .li:last-child{border-bottom:0}
.list .li .why{grid-column:1/-1;color:var(--mute);font-size:12.5px}
.tblwrap{background:var(--card);border-radius:8px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{padding:6px 4px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left;padding-left:8px}
th:last-child,td:last-child{padding-right:8px}
th{font-weight:600;color:var(--mute);font-size:11px;position:sticky;top:0;background:var(--card)}
th button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}
th button[aria-pressed="true"]{color:var(--ink);text-decoration:underline}
tr:last-child td{border-bottom:0}
td a{color:inherit;text-decoration:none;display:block;line-height:1.25}
td.sg{border-left:3px solid transparent} td.sg.left{border-left-color:var(--left)} td.sg.right{border-left-color:var(--up)} td.sg.sell{border-left-color:var(--warn)}
td b.hot{font-weight:700}
.tiles2{display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));gap:8px}
.mt{background:var(--card);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:3px;min-width:0;scroll-margin-top:52px}
.mt .t{display:flex;justify-content:space-between;gap:6px;font-size:13px;align-items:baseline}
.mt .t b{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.25}
.mt svg{width:100%;height:46px;display:block}
.mt .s{font-size:11.5px;color:var(--mute);line-height:1.45}
.plan{background:var(--soft);border-radius:6px;padding:7px 10px;font-size:13px;display:flex;flex-direction:column;gap:1px}
.plan b{font-weight:600}
.chip{display:inline-block;font-size:11.5px;line-height:1.5;padding:0 6px;border-radius:4px;border:1px solid var(--line);color:var(--mute);white-space:nowrap}
.chip.left{color:var(--left);border-color:var(--left)} .chip.right{color:var(--up);border-color:var(--up)}
.chip.sell{color:var(--warn);border-color:var(--warn)} .chip.new{background:var(--ink);color:var(--card);border-color:var(--ink)}
.chips{display:flex;gap:4px;flex-wrap:wrap}
.empty{background:var(--card);border-radius:8px;padding:12px 14px;color:var(--mute);font-size:13.5px}
.rsi{background:var(--card);border-radius:8px;padding:10px 14px 12px}
.rsi .row{display:grid;grid-template-columns:96px 1fr 40px;gap:8px;align-items:center;min-height:32px;font-size:13px}
.rsi .row .n{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.2}
.cd{display:block;font-family:var(--num);font-size:11px;color:var(--mute);font-weight:400}
.ci{font-family:var(--num);font-size:11.5px;color:var(--mute);font-weight:400;margin-left:3px}
.track{position:relative;height:10px;border-radius:2px;background:linear-gradient(90deg,
  color-mix(in srgb,var(--left) 55%,transparent) 0 10%,color-mix(in srgb,var(--left) 35%,transparent) 10% 20%,
  color-mix(in srgb,var(--left) 18%,transparent) 20% 30%,var(--soft) 30% 70%,
  color-mix(in srgb,var(--warn) 22%,transparent) 70% 80%,color-mix(in srgb,var(--warn) 45%,transparent) 80% 100%)}
.track i{position:absolute;top:-3px;width:10px;height:16px;margin-left:-5px;border-radius:3px;background:var(--ink);border:2px solid var(--card)}
.axis{display:grid;grid-template-columns:96px 1fr 40px;gap:8px;font-size:11px;color:var(--mute)}
.axis div{position:relative;height:16px}
.axis span{position:absolute;transform:translateX(-50%)}
.etf{background:var(--card);border-radius:8px;padding:12px 14px;display:flex;flex-direction:column;gap:8px}
.etf .top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.etf .nm{font-weight:700}
.etf .nm small{font-weight:400;font-size:12px;color:var(--mute);margin-left:4px}
.etf .px{text-align:right;white-space:nowrap}
.etf .px b{font-size:16px}
.mid{display:flex;gap:10px;align-items:center}
.mid svg{flex:none;width:150px;height:48px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;font-size:13px}
.kv dt{color:var(--mute);white-space:nowrap} .kv dd{margin:0}
.big{font-size:20px;font-weight:700;line-height:1}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--mute)}
.legend i{display:inline-block;width:14px;height:0;border-top:2px solid;vertical-align:middle;margin-right:4px}
.cat{font-size:13px;font-weight:600;color:var(--mute);grid-column:1/-1;margin-top:4px}
details{background:var(--card);border-radius:8px;padding:10px 14px}
summary{cursor:pointer;font-weight:600}
details ol,details ul{margin:8px 0 0;padding-left:20px;font-size:13.5px}
details li{margin:4px 0}
dl.gloss{margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px 20px;font-size:13.5px}
dl.gloss div{break-inside:avoid}
dl.gloss dt{font-weight:600} dl.gloss dd{margin:0;color:var(--mute)}
.foot{font-size:12px;color:var(--mute)}
"""

JS = """
(function(){
  var tb=document.querySelector('#ov tbody'); if(!tb) return;
  var btns=document.querySelectorAll('#ov th button');
  btns.forEach(function(b){b.addEventListener('click',function(){
    var k=b.dataset.k, on=b.getAttribute('aria-pressed')==='true', dir=on?-(+b.dataset.dir||1):(+b.dataset.d);
    btns.forEach(function(x){x.setAttribute('aria-pressed','false')});
    b.setAttribute('aria-pressed','true'); b.dataset.dir=dir;
    [].slice.call(tb.rows).sort(function(a,c){return dir*(a.dataset[k]-c.dataset[k])}).forEach(function(r){tb.appendChild(r)});
  })});
})();
"""

FLAG_CN = {"hv": "高波动品种", "fx": "含汇率波动", "div": "高分红", "fut": "期货·有展期损耗", "gap": "休市时标的也在动"}

GLOSSARY = [
    ("RSI14（相对强弱指标）", "衡量最近14个交易日涨跌力度的0~100读数。低于30叫超卖（跌得急，容易反抽），低于20、10更极端；高于70叫超买（涨得急，容易回落）。"),
    ("左侧 / 右侧", "左侧：还在跌的时候分批买，赌反抽，买得便宜但可能继续跌。右侧：等涨势确认后再跟，买得贵一点但方向更明确。"),
    ("低 / 中 / 高波动品种", "按这只ETF近一年平均每天的波动（ATR%中位数）分组：低于1.2%算低波动（如SPY、必需消费），高于2.5%算高波动（如半导体、比特币）。低波动品种跌破RSI 30就很少见，所以第一档买得多；高波动品种常常跌得更深，子弹留到后面。"),
    ("MA（均线）", "最近N天收盘价的平均值。MA3、MA5、MA7看短线方向；MA20看一个月趋势；MA60看一个季度。"),
    ("200日线", "最近200个交易日的平均价，美股最常用的牛熊分界线。价格在它上方的回调更值得买，在它下方的超卖可能是“下跌中继”，所以本报告的左侧仓位在线下减半。"),
    ("三线同步向上", "MA3、MA5、MA7今天都比昨天高。本报告还要求MA3>MA5>MA7且连续至少2天，才算右侧信号的均线条件。"),
    ("多头排列 / 空头排列", "短期均线在上、长期均线在下且一起向上，是多头排列（上升趋势）；反过来是空头排列（下降趋势）。互相缠在一起叫均线缠绕（震荡）。"),
    ("量比", "今天成交量 ÷ 过去5天平均成交量。大于1.2算温和放量，大于1.5算明显放量。盘中报告已按美股U形成交分布折算成全天。"),
    ("MACD", "由两条线组成的趋势指标：快线DIF、慢线DEA。两条线都在0上方（0轴上方）说明中期趋势向上。"),
    ("金叉 / 死叉 / 金叉中期", "DIF向上穿过DEA叫金叉，向下穿过叫死叉。本报告把金叉后第1~3天叫初期，第4~10天叫中期（趋势走出来了但还没走老），10天以上叫后期。"),
    ("动能增强 / 减弱", "MACD红绿柱（DIF与DEA的差距）比昨天变长还是变短。变短说明这段走势在减速。"),
    ("乖离（BIAS）", "现价偏离20日均线的百分比。本报告用“乖离是ATR%的几倍”来判断追高风险，超过3倍提示别追：SPY乖离3%就很极端，铀ETF乖离9%才算。"),
    ("波动 / 波动率", "价格上下起伏的剧烈程度。报告里的波动率是按最近20天日涨跌幅折算的年化数字，越大越颠簸。"),
    ("ATR / ATR%", "平均真实波幅：最近14天平均每天上下波动多少美元。ATR%是它占现价的比例，例如2%表示平均每天波动2%。用来定止损距离和仓位。"),
    ("高波动（当前）", "当前ATR%处在这只ETF自己近一年的前20%高位。这时同样仓位风险更大，仓位减半。"),
    ("RS（相对强弱）", "这只ETF最近20天的涨幅，减去标普500ETF（SPY）同期涨幅。正数说明比大盘强；排名是在本池内从强到弱的名次。注意它和RSI不是一回事。"),
    ("回撤（距高点跌幅）", "现价比某个最高价低了百分之多少。距历史高点用数据里最早到今天的最高价，距60日高点用最近60个交易日的最高价。"),
    ("税后复权价", "把拆股和分红造成的价格跳变抹平后的价格，分红按扣掉10%预扣税后再投入计算，这样不同时期的价格可比，也贴近中国投资者真实到手的收益。"),
    ("跳空", "今天开盘价和昨天收盘价之间的缺口。美股没有涨跌停，坏消息常在盘前消化，开盘可能直接跌穿你的止损价，所以止损价不等于成交价。"),
    ("吊灯止盈线", "最近22天最高价减去3倍ATR。价格涨它跟着抬，价格跌它不动；收盘跌破就离场，用来保护右侧单的利润。"),
    ("止损", "买入前就定好的认错价位。本报告右侧信号的初始止损 = 买入价 − 2倍ATR。"),
    ("仓位%", "建议这只ETF占你总资金的比例。算法：单笔最多亏总资金的1%，再除以止损距离，且单只不超过20%。"),
    ("市场温度 / 参考总仓位上限", "综合池内站上20日线的比例、平均RSI、MACD在0轴上方的比例得到的0~100分。低于20冰点，高于80过热。越冷允许的总仓位越高，是逆向思路的粗略参考。"),
    ("VIX（恐慌指数）", "由标普500期权价格算出的市场预期波动率。低于13偏平静（容易自满），20~30紧张，30以上恐慌。恐慌时往往是分批买宽基的时机。"),
    ("FOMC / CPI / 非农", "美联储利率会议、通胀数据、就业数据，美股三大宏观事件，发布当天波动常常放大。本报告在事件前2个交易日把右侧新开仓减半。"),
    ("成分调整（优胜劣汰）", "指数按固定规则定期剔除不达标的公司、纳入新达标的公司，ETF跟着调仓。比如罗素2000每年6月、12月重构，SCHD每年3月按分红质量重选100只。本池只选这类规则化指数ETF。"),
    ("规模 / 日均成交额 / 买卖价差", "规模越大越不容易清盘；日均成交额越大越容易买进卖出；买卖价差是买一和卖一之间的差，越小交易成本越低。本池门槛：规模10亿美元以上、日均成交3000万美元以上。"),
    ("相关性 / 高度同向", "两只ETF最近60天涨跌同步的程度，1为完全同步。高于0.8时同时买两只等于重复下注，只做其中更强的一只。"),
    ("预扣税 / W-8BEN", "非美国人持有美国ETF，分红会先被代扣税。在券商填写W-8BEN表后，中国税务居民一般按中美税收协定扣10%。不构成税务建议。"),
    ("历史表现（胜率）", "这只ETF历史上同一信号首次出现后，持有10个交易日的结果统计。次数少于5次时参考价值很低。"),
]

DISCIPLINE = [
    ("先不亏，再谈赚", "借鉴巴菲特的安全边际思路：200日线下方的超卖仓位减半；没有信号的日子，结论就是不动。"),
    ("不做清单", "借鉴段永平的做法：不加杠杆、不做空、不买杠杆/反向ETF、看不懂的品种不碰；期货类ETF不长拿。"),
    ("跟着流动性走", "借鉴孙宇晨重视热度与流动性的打法：右侧只做放量的、RS排名靠前的；高波动品种单只上限减半，错了成本低。"),
    ("等关键点，不摊平亏损", "借鉴利弗莫尔的趋势交易原则：右侧优先贴近60日新高的突破；左侧最多三档，打满后只止损不加仓。"),
    ("别把同一个赌注下两遍", "借鉴达利欧的分散思路：高度同向的ETF只选最强一只，股、债、金、海外互相对冲。"),
    ("让波动决定仓位", "借鉴海龟交易法：用ATR算止损和仓位，波动大的少买，单笔亏损不超过总资金的1%。"),
]


def usd_m(v):
    """百万美元 -> $1.2B / $350M。"""
    if v is None:
        return "—"
    return f"${v / 1000:,.1f}B" if v >= 1000 else f"${v:,.0f}M"


def pct(v, nd=1, color=True):
    if v is None:
        return '<span class="mute">—</span>'
    cls = ("up" if v > 0 else "down" if v < 0 else "") if color else ""
    return f'<span class="num {cls}">{v:+.{nd}f}%</span>'


def spark(sp, w=150, h=46):
    vals = [v for s in sp.values() for v in s if v is not None]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(sp["close"])

    def path(arr):
        pts, cmd = [], "M"
        for i, v in enumerate(arr):
            if v is None:
                cmd = "M"
                continue
            pts.append(f"{cmd}{2 + i * (w - 8) / max(n - 1, 1):.1f},{3 + (hi - v) / rng * (h - 6):.1f}")
            cmd = "L"
        return "".join(pts)

    colors = {"ma5": "var(--s1)", "ma20": "var(--s2)", "ma60": "var(--s3)"}
    out = [f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
           f'aria-label="近60日收盘价与MA5、MA20、MA60走势">']
    for k in ("ma60", "ma20", "ma5"):
        out.append(f'<path d="{path(sp[k])}" fill="none" stroke="{colors[k]}" stroke-width="1.2" vector-effect="non-scaling-stroke"/>')
    out.append(f'<path d="{path(sp["close"])}" fill="none" stroke="var(--ink)" stroke-width="1.6" '
               f'stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>')
    return "".join(out)


def stats_line(st):
    if not st or st.get("n", 0) == 0:
        return "历史上这只ETF没出现过同样信号，无从参考"
    weak = "（样本少，参考价值低）" if st["n"] < 5 else ""
    return (f'历史上出现过 {st["n"]} 次，{st["fwd"]} 个交易日后上涨占 {st["win"]:.0f}%，'
            f'平均 {st["avg"]:+.1f}%，最差 {st["worst"]:+.1f}%{weak}')


def flag_chips(r):
    return "".join(f'<span class="chip">{E(FLAG_CN[f])}</span>' for f in r["flags"])


def name_px(r):
    return (f'<div class="top"><span class="nm">{E(r["name"])}<small class="num">{r["code"]}</small></span>'
            f'<span class="num"><b>{r["close"]}</b> {pct(r["chg"], 2)}</span></div>')


def opp_card(r, s):
    kind = s["kind"]
    fresh = s.get("fresh") if s.get("fresh") is not None else s.get("is_new")
    chips = f'<div class="chips"><span class="chip {kind}">{E(s["title"])}</span>'
    if fresh:
        chips += '<span class="chip new">新</span>'
    if kind == "left":
        chips += f'<span class="chip">{"已止跌回升" if s["turning"] else "尚未止跌"}</span>'
    else:
        chips += f'<span class="chip">启动第 {s["days"]} 天</span>'
    chips += flag_chips(r) + "</div>"
    cut = f'（已含{"、".join(s["cuts"])}）' if s["cuts"] else ""
    if kind == "left":
        key = (f'RSI14 <b class="num">{r["rsi"]:.1f}</b>，连续超卖 {s["days"]} 天 · '
               f'距60日高点 <span class="num">{r["dd_60"]:.1f}%</span>')
        plan = (f'<div><b>仓位</b> 累计不超过总资金 {s["pos"]:.0f}%{cut}</div>'
                f'<div><b>目标</b> 反抽到 MA20 <span class="num">${s["target"]}</span>（{s["target_pct"]:+.1f}%）减仓</div>')
        more = [f'认错：{s["stop_note"]}']
    else:
        key = (f'三线同步向上 {r["ma_up_days"]} 天 · 量比 <b class="num">{r["vol_ratio"]:.2f}</b> · '
               f'RS 池内第 {r["rs_rank"]}')
        plan = (f'<div><b>仓位</b> 不超过总资金 {s["pos"]:.0f}%{cut}</div>'
                f'<div><b>止损</b> <span class="num">${s["stop"]}</span>（−{s["stop_pct"]:.1f}%）'
                f' · <b>止盈线</b> <span class="num">${s["trail"]}</span></div>')
        more = ["止盈：收盘跌破吊灯止盈线就离场，这条线会随新高上移"]
    more = list(s["why"]) + more + [stats_line(s.get("stats"))]
    if "gap" in r["flags"]:
        more.append("比特币周末和夜里照常交易，周一开盘可能大幅跳空，止损价不一定成交得到")
    if "fx" in r["flags"]:
        more.append("海外市场ETF：涨跌里含当地货币兑美元的变化，当地夜里已收盘，美股开盘时价格反映的是隔夜消息")
    if "fut" in r["flags"]:
        more.append("期货类ETF：只做波段，不长期持有")
    if s.get("twins"):
        more.append("与 " + "、".join(s["twins"]) + " 高度同向，只选 RS 更强的一只")
    detail = ('<details><summary>依据、认错条件与历史表现</summary><ul>'
              + "".join(f"<li>{E(x)}</li>" for x in more) + "</ul></details>")
    return (f'<article class="opp {kind}">{name_px(r)}{chips}<div class="key">{key}</div>'
            f'<div class="plan">{plan}</div>{detail}</article>')


def action_list(left, right, sell, info) -> str:
    """今晚操作清单：只在收盘报告里出现，给下一个开盘的挂单参考。"""
    if info["session"] != "close":
        return ""
    items = []
    for r, s in right:
        lim = r["close"] + 0.5 * r["atr_pct"] / 100 * r["close"]
        items.append(f'<li><b class="up">买</b> {E(r["name"])}<span class="ci">{r["code"]}</span> 仓位 ≤{s["pos"]:.0f}%，'
                     f'限价 ≤ <span class="num">${lim:.2f}</span>（高开超过半个 ATR 就不追），止损 <span class="num">${s["stop"]}</span></li>')
    for r, s in left:
        items.append(f'<li><b style="color:var(--left)">吸</b> {E(r["name"])}<span class="ci">{r["code"]}</span> 本档仓位 ≤{s["pos"]:.0f}%，'
                     f'限价 ≤ <span class="num">${r["close"]:.2f}</span>（昨收，不追高开）'
                     + ("" if s["turning"] else "，尚未止跌，只买第一笔") + '</li>')
    for r in sell:
        g = max(x["grade"] for x in r["sell"])
        what = "清仓" if any(x["title"] == "破止盈线" for x in r["sell"]) else "卖一半" if g >= 2 else "收紧止盈到"
        tail = f' <span class="num">${r["chandelier"]}</span>' if what == "收紧止盈到" else "，开盘市价单"
        items.append(f'<li><b style="color:var(--warn)">抛</b> 持有 {E(r["name"])}<span class="ci">{r["code"]}</span> 的：{what}{tail}</li>')
    if not items:
        return ('<div class="plan"><b>今晚操作：不动。</b>没有新信号，持仓按原止损/止盈线管理。</div>')
    t = info.get("next_open_bj", "")
    return (f'<div class="plan"><b>今晚操作清单</b>（下一次开盘：北京时间 {E(t)}，开盘前挂好单即可，不用熬夜盯盘）'
            f'<ol style="margin:4px 0 0;padding-left:20px">{"".join(items[:8])}</ol>'
            + ("<div class='mute'>信号较多，只列前 8 条，其余见下方。</div>" if len(items) > 8 else "")
            + '<div class="mute">两个以上高度同向的只做 RS 更强的一只；总仓位别超过上面的参考上限。</div></div>')


def sell_row(r):
    chips = "".join(f'<span class="chip sell">{E(s["title"])}</span>'
                    + ('<span class="chip new">新</span>' if s.get("fresh") else "") for s in r["sell"])
    why = "；".join(s["why"] for s in r["sell"])
    return (f'<div class="li"><div><b>{E(r["name"])}</b><span class="ci">{r["code"]}</span> <span class="chips" style="display:inline-flex">{chips}</span></div>'
            f'<div class="num">{r["close"]} {pct(r["chg"], 2)}</div>'
            f'<div class="why">{E(why)} · 止盈线 {r["chandelier"]}</div></div>')


def dd(v):
    return "新高" if v > -0.5 else f"{v:.0f}%"


def ov_row(r, i):
    kind = (r["buy"][0]["kind"] if r["buy"] else "sell" if r["sell"] else "")
    rsi = r["rsi"]
    rcls = "down" if rsi < 30 else "up" if rsi >= 70 else ""
    lv = min(r["rsi_below"]) if r["rsi_below"] else None
    tag = f'<span class="cd {rcls}">破{lv}</span>' if lv else ('<span class="cd up">超买</span>' if rsi >= 70 else "")
    arrows = "".join('<span class="up">↑</span>' if u else '<span class="down">↓</span>' for u in r["ma_dirs"])
    ma_n = r["ma_up_days"] or -r["ma_dn_days"]
    vr = r["vol_ratio"] or 0
    vr_html = f'<b class="hot">{vr:.2f}</b>' if vr >= C.VOL_RATIO_OK else f"{vr:.2f}"
    m = r["macd"]
    mk = ("上" if m["above"] else "下" if m["pos"] == "0轴下方" else "穿") + "·" + ("金" if m["golden"] else "死") + str(m["days"])
    if m["above"] and m["mid_golden"]:
        mk = f'<b class="hot up">{mk}</b>'
    macd_key = (2 if m["above"] else 0) + (1 if m["golden"] else 0)
    return (f'<tr data-ord="{i}" data-rsi="{rsi}" data-ma="{ma_n}" data-vr="{vr}" data-macd="{macd_key}" '
            f'data-ath="{r["dd_ath"]}" data-d60="{r["dd_60"]}">'
            f'<td class="sg {kind}"><a href="#e{r["code"]}">{E(r["name"].replace("ETF", ""))}<span class="cd">{r["code"]}</span></a></td>'
            f'<td class="num {rcls}"><b>{rsi:.1f}</b>{tag}</td><td>{arrows}</td><td class="num">{vr_html}</td>'
            f'<td class="num">{mk}</td><td class="num">{dd(r["dd_ath"])}<span class="cd">{dd(r["dd_60"])}</span></td></tr>')


def ma_tile(r):
    if r["ma_up_days"]:
        ma_txt = f'三线同升 {r["ma_up_days"]} 天'
    elif r["ma_dn_days"]:
        ma_txt = f'三线同降 {r["ma_dn_days"]} 天'
    else:
        ma_txt = "三线方向不一"
    year = "" if r["above_year"] is None else (" · 200日线上方" if r["above_year"] else " · 200日线下方")
    m = r["macd"]
    tags = (["当前高波动"] if r["high_vol"] else []) + [FLAG_CN[f] for f in r["flags"] if f != "hv"] + [C.GROUP_CN[r["group"]]]
    tag_html = f'<div class="s">{E(" · ".join(tags))}</div>' if tags else ""
    return (f'<article class="mt" id="e{r["code"]}"><div class="t"><b>{E(r["name"])}<span class="cd">{r["code"]}</span></b>{pct(r["chg"], 2)}</div>'
            f'{spark(r["spark"])}'
            f'<div class="s"><b style="color:var(--ink)">{E(r["pattern"])}</b>{year}</div>'
            f'<div class="s">{ma_txt} · MACD {E(m["cross"])}</div>'
            f'<div class="s num">RS {r["rs"]:+.1f} · 乖离 {r["bias"]:+.1f}% · ATR {r["atr_pct"]:.1f}%</div>'
            f'<div class="s num">成交 {usd_m(r["amount_m"])} · 历史高点 {r["ath_date"]}</div>{tag_html}</article>')


SESSION_CN = {"mid": ("盘中快照", "noon"), "close": ("收盘定稿", "")}


def render(res: dict, info: dict) -> str:
    rows, t = res["rows"], res["temp"]
    session = info["session"]
    left = sorted([(r, s) for r in rows for s in r["buy"] if s["kind"] == "left"],
                  key=lambda x: (not x[1]["turning"], -x[1]["grade"], x[0]["rsi"]))
    right = sorted([(r, s) for r in rows for s in r["buy"] if s["kind"] == "right"],
                   key=lambda x: (-x[1]["grade"], x[0]["rs_rank"]))
    sell = sorted([r for r in rows if r["sell"]], key=lambda r: (-max(s["grade"] for s in r["sell"]), -r["rsi"]))
    watch = [r for r in rows if r["watch"]]

    def names(lst, k=3):
        ns = [f'{y["name"].replace("ETF", "")}({y["code"]})' for y in (x[0] if isinstance(x, tuple) else x for x in lst[:k])]
        return "、".join(ns) + ("等" if len(lst) > k else "")

    if not left and not right and not sell:
        lead = "今天没有触发任何信号，结论是不动。"
    else:
        parts = [f"可低吸 {names(left)}" if left else "没有超卖可吸",
                 f"可跟随 {names(right)}" if right else "没有放量启动"]
        if sell:
            parts.append(f"持有 {names(sell)} 的考虑止盈")
        lead = "，".join(parts) + "。"

    title = "美股 ETF 低吸高抛日报"
    sn, scls = SESSION_CN[session]
    srcs = sorted({SOURCE_CN.get(r["source"], r["source"]) for r in rows})
    h = [f'<header class="head"><h1>{title}</h1>'
         f'<div class="meta"><span class="badge {scls}">{sn}</span><span>行情日 {info["date"]}</span>'
         f'<span>北京 {info["generated_bj"][5:]} 生成（美东 {info["generated"][-5:]}）</span><span>{len(rows)} 只 · {E("、".join(srcs))}</span>'
         f'<a href="sim.html">模拟盘收益 →</a></div></header>']
    if info.get("demo"):
        h.append('<div class="banner"><b>演示数据。</b>本页价格与信号由程序模拟生成，只用来展示版面，不是真实行情，不能据此交易。</div>')
    if session != "close":
        h.append(f'<div class="banner">{sn}，尚未收盘：量比已按时段折算，信号都是临时的，以收盘报告为准（北京时间次日早上生成）。</div>')
    if info.get("problems"):
        h.append('<div class="banner"><b>数据提醒：</b>' + E("；".join(info["problems"])) + "</div>")

    h.append(f'<p class="lead">{E(lead)}</p>')
    h.append(action_list(left, right, sell, info))
    vx = t.get("vix")
    vix_tile = (f'<a class="tile t" href="#gloss"><b class="num">{vx["value"]}</b><span>VIX·{vx["label"]}</span></a>'
                if vx else "")
    h.append(f'''<div class="tiles">
<a class="tile l" href="#left"><b class="num">{len(left)}</b><span>左侧低吸</span></a>
<a class="tile r" href="#right"><b class="num">{len(right)}</b><span>右侧启动</span></a>
<a class="tile s" href="#sell"><b class="num">{len(sell)}</b><span>高抛提示</span></a>
<a class="tile t" href="#gloss"><b class="num">{t["score"]}</b><span>温度·{t["label"]}</span></a>{vix_tile}</div>''')
    sub = [f'市场温度 {t["score"]}（{t["label"]}）：{t["hint"]}。参考总仓位上限 {t["cap"]}%。',
           f'近20日最强 {"、".join(res["strong"])}；最弱 {"、".join(res["weak"])}。'
           f'站上20日线 {t["above20"]}%，平均RSI {t["avg_rsi"]}。']
    if res.get("hot"):
        sub.append(f'资金最活跃（近5日成交额 ÷ 近60日均值）：{"、".join(res["hot"])}。')
    if vx:
        sub.append(f'VIX {vx["value"]}（{vx["chg"]:+.1f}，近一年 {vx["pctl"]}% 分位）：{vx["hint"]}。')
    if res["gone"]:
        sub.append("较上一期消失的信号：" + "、".join(res["gone"][:6]) + "。")
    h.append('<div class="sub">' + "".join(f"<div>{E(x)}</div>" for x in sub) + "</div>")
    ev = info.get("events") or []
    if ev:
        h.append('<div class="banner"><b>近期事件：</b>' + "；".join(
            f'{e["date"].strftime("%m-%d")} {E(e["title"])}' + (f'（{"、".join(e["codes"])}）' if e["codes"] else "")
            for e in ev[:6]) + ("。<b>2 个交易日内有宏观大事件，右侧新开仓已减半。</b>" if info.get("macro_soon") else "。")
            + "</div>")
    h.append('<nav><a href="#left">左侧</a><a href="#right">右侧</a><a href="#sell">高抛</a>'
             '<a href="#ov">总览表</a><a href="#rsi">RSI排行</a><a href="#ma">均线图</a><a href="#pool">池子</a><a href="#gloss">术语</a><a href="sim.html">模拟盘 →</a></nav>')

    h.append('<section id="left"><h2>左侧低吸 <small>RSI14 跌破 30 / 20 / 10，博反抽</small></h2>')
    h.append('<div class="grid">' + "".join(opp_card(r, s) for r, s in left) + "</div>" if left
             else '<div class="empty">今天没有 RSI14 低于 30 的标的，不硬找。</div>')
    h.append("</section>")
    h.append('<section id="right"><h2>右侧启动 <small>MA3/5/7 同步向上 + 放量，启动 3 天内</small></h2>')
    h.append('<div class="grid">' + "".join(opp_card(r, s) for r, s in right) + "</div>" if right
             else '<div class="empty">今天没有刚启动的放量拉升。</div>')
    h.append("</section>")
    h.append('<section id="sell"><h2>高抛提示 <small>只对已持有的人有用</small></h2>')
    h.append('<div class="list">' + "".join(sell_row(r) for r in sell) + "</div>" if sell
             else '<div class="empty">今天没有超买或破位的标的。</div>')
    if watch:
        h.append(f'<details><summary>观察名单 {len(watch)} 只：快到信号边上，或趋势延续中</summary><ul>'
                 + "".join(f'<li><b>{E(r["name"])}</b><span class="ci">{r["code"]}</span>：{E("；".join(r["watch"]))}</li>' for r in watch) + "</ul></details>")
    rv = res["review"]
    if rv:
        wins = sum(1 for x in rv if x["ret"] > 0)
        avg = sum(x["ret"] for x in rv) / len(rv)
        h.append(f'<details><summary>近 {C.REVIEW_DAYS} 日信号回顾：共 {len(rv)} 次，至今上涨 {wins} 次，平均 {avg:+.1f}%</summary><ul>'
                 + "".join(f'<li><span class="num">{x["date"]}</span> {E(x["name"])}<span class="ci">{x["code"]}</span> {E(x["title"])}，'
                           f'{x["days"]} 天后 {pct(x["ret"])}</li>' for x in rv[:30]) + "</ul></details>")
    h.append("</section>")

    # 总览表
    def th(label, k, d):
        return f'<th><button data-k="{k}" data-d="{d}" aria-pressed="false">{label}</button></th>'
    h.append('<section id="ov"><h2>全池总览 <small>点表头排序，点名称看均线图</small></h2><div class="tblwrap"><table><thead><tr>'
             + th("名称", "ord", 1) + th("RSI14", "rsi", 1) + th("三线", "ma", -1) + th("量比", "vr", -1)
             + th("MACD", "macd", -1) + th("回撤<br>历史/60日", "ath", 1) + "</tr></thead><tbody>")
    i = 0
    for cat in C.CAT_ORDER:
        for r in (x for x in rows if x["cat"] == cat):
            h.append(ov_row(r, i))
            i += 1
    h.append('</tbody></table></div><div class="foot">名称左侧色条：蓝 = 左侧低吸，红 = 右侧启动，黄 = 高抛提示。'
             '三线 = MA3、MA5、MA7 今天各自的方向。MACD 列：上 / 下 = 在0轴上方 / 下方，穿 = 正在穿越；金5 = 金叉第5天，死3 = 死叉第3天；红色加粗 = 0轴上方的金叉中期。'
             '量比加粗 = 放量（≥1.2）。回撤列上面是距历史最高价、下面是距近 60 日最高价的跌幅，点表头按历史回撤排序。</div></section>')

    # RSI 排行
    h.append('<section id="rsi"><h2>RSI14 排行 <small>左边蓝区超卖，右边黄区超买</small></h2><div class="rsi">')
    h.append('<div class="axis"><div></div><div>' + "".join(
        f'<span style="left:{v}%">{v}</span>' for v in (10, 20, 30, 50, 70, 80)) + "</div><div></div></div>")
    for r in sorted(rows, key=lambda x: x["rsi"]):
        cls = "down" if r["rsi"] < 30 else "up" if r["rsi"] >= 70 else ""
        h.append(f'<div class="row"><span class="n">{E(r["name"].replace("ETF", ""))}<span class="cd">{r["code"]}</span></span>'
                 f'<div class="track" title="{E(r["name"])} RSI14 {r["rsi"]}"><i style="left:{min(max(r["rsi"], 1), 99)}%"></i></div>'
                 f'<span class="num {cls}" style="text-align:right;font-weight:600">{r["rsi"]:.1f}</span></div>')
    h.append("</div></section>")

    # 均线图形
    h.append('<section id="ma"><h2>均线图形 <small>近 60 个交易日</small></h2>')
    h.append('<div class="legend"><span><i style="border-color:var(--ink)"></i>收盘价</span>'
             '<span><i style="border-color:var(--s1)"></i>MA5</span><span><i style="border-color:var(--s2)"></i>MA20</span>'
             '<span><i style="border-color:var(--s3)"></i>MA60</span></div><div class="tiles2">')
    for cat in C.CAT_ORDER:
        grp = [r for r in rows if r["cat"] == cat]
        if grp:
            h.append(f'<div class="cat">{E(cat)} · {len(grp)} 只</div>' + "".join(ma_tile(r) for r in grp))
    h.append("</div></section>")

    # 池子与成分规则
    h.append('<section id="pool"><h2>池子与成分规则 <small>每只都跟踪规则化指数，成分定期优胜劣汰</small></h2>'
             '<div class="tblwrap"><table><thead><tr><th>ETF</th><th style="text-align:left">跟踪指数 · 成分调整</th>'
             '<th>档</th><th>日成交</th></tr></thead><tbody>')
    for cat in C.CAT_ORDER:
        for r in (x for x in rows if x["cat"] == cat):
            h.append(f'<tr><td>{E(r["name"].replace("ETF", ""))}<span class="cd">{r["code"]} · {E(cat)}</span></td>'
                     f'<td style="text-align:left;white-space:normal;min-width:220px">{E(r["index"])}<span class="cd" style="font-family:var(--font)">{E(r["recon"])}</span></td>'
                     f'<td class="num">{r["tier"]}</td><td class="num">{usd_m(r["amount_m"])}</td></tr>')
    h.append('</tbody></table></div><div class="foot">ETF 本身也优胜劣汰：每月运行 <code>python -m us_etf_monitor.pool_audit</code>，'
             '比较规模、日均成交额、买卖价差，同赛道候选连续明显更好就换。</div></section>')
    h.append('<section id="rules"><details><summary>操作纪律六条（多流派智囊团的共识）</summary><ol>'
             + "".join(f"<li><b>{E(a)}</b>：{E(b)}</li>" for a, b in DISCIPLINE) + "</ol></details>")
    h.append('<div class="foot">本报告由程序按固定规则自动生成，只做信息整理，不构成投资建议。信号是候选名单，下单前请自己复核。'
             '历史统计不代表未来。</div></section>')
    h.append('<section id="gloss"><h2>术语解释</h2><dl class="gloss">'
             + "".join(f"<div><dt>{E(a)}</dt><dd>{E(b)}</dd></div>" for a, b in GLOSSARY) + "</dl></section>")

    return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title}</title><style>{CSS}</style></head><body><div class="wrap">'
            + "\n".join(h) + f"</div><script>{JS}</script></body></html>")


def text_summary(res: dict, info: dict, url: str = "") -> str:
    """给飞书推送用的纯文本摘要。"""
    rows, t = res["rows"], res["temp"]
    vx = t.get("vix")
    lines = [f"【美股】ETF日报 {info['date']} {SESSION_CN[info['session']][0]}｜温度 {t['score']} {t['label']}"
             + (f"｜VIX {vx['value']}" if vx else "")]
    L = [(r, s) for r in rows for s in r["buy"] if s["kind"] == "left"]
    R = [(r, s) for r in rows for s in r["buy"] if s["kind"] == "right"]
    S = [r for r in rows if r["sell"]]
    lines.append("左侧低吸：" + ("、".join(f"{r['name']}{r['code']}(RSI {r['rsi']:.0f})" for r, _ in L) or "无"))
    lines.append("右侧启动：" + ("、".join(f"{r['name']}{r['code']}(量比 {r['vol_ratio']:.1f})" for r, _ in R) or "无"))
    lines.append("高抛提示：" + ("、".join(f"{r['name']}{r['code']}({'/'.join(x['title'] for x in r['sell'])})" for r in S) or "无"))
    if url:
        lines.append(url)
    return "\n".join(lines)
