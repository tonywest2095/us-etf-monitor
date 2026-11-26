"""美股 ETF 池与全部可调参数。改池子、改阈值只动这一个文件。

所有时间以美东时间（America/New_York）为准，夏令时由程序自动处理。
"""

# ---------------------------------------------------------------------------
# ETF 池：tier=1 为 10 只核心档，tier<=2 为 20 只档，tier<=3 为 30 只档（上限 30）
#
# 选池规则
#   1. 每个赛道只留一只：规模（AUM）大、成交活跃、买卖价差小、主要持仓与名称相符。
#      alts 是同赛道的候选，pool_audit.py 每月比一次，候选连续两个月明显更好就换。
#   2. 成分"优胜劣汰"：只选跟踪规则化指数、定期调整成分的 ETF（index / recon 两栏写明规则），
#      不选成分长期不动的主动或主题拼盘产品。
#   3. 不入池：杠杆 / 反向 ETF（长期有损耗）、发 K-1 税表的合伙制基金（海外投资者处理麻烦）。
#
# flags
#   hv   = 高波动品种：单只上限降到 SIM_MAX_POS_HV，信号仓位再打折
#   fx   = 海外市场，含当地货币兑美元的汇率波动
#   div  = 高分红：价格必须复权，否则历史高点和回撤失真
#   fut  = 持有期货合约，有展期损耗，只做波段
#   gap  = 标的资产在美股休市时也在交易（比特币），开盘跳空大
# ---------------------------------------------------------------------------
POOL = [
    # ---- 第一档：10 只核心 ----
    dict(code="SPY", name="标普500ETF", cat="宽基", tier=1, flags=[], alts=["VOO", "IVV"],
         index="S&P 500", recon="成分随时增删（市值、盈利、流动性达标才入选），每季度第三个周五再平衡"),
    dict(code="IWM", name="罗素2000小盘ETF", cat="小盘", tier=1, flags=[], alts=["VTWO", "IJR"],
         index="Russell 2000", recon="2026 年起每年 6 月、12 月两次重构，按市值重新划分大小盘"),
    dict(code="SCHD", name="美国红利ETF", cat="红利", tier=1, flags=["div"], alts=["VYM", "DGRO"],
         index="Dow Jones U.S. Dividend 100", recon="每年 3 月重构：连续 10 年分红 + 现金流、ROE、股息率、股息增长打分选前 100"),
    dict(code="GLD", name="黄金ETF", cat="商品", tier=1, flags=[], alts=["IAU", "GLDM"],
         index="伦敦金价（实物黄金）", recon="实物持有，无成分调整"),
    dict(code="KWEB", name="中概互联ETF", cat="海外", tier=1, flags=["fx", "hv"], alts=["FXI", "MCHI"],
         index="CSI Overseas China Internet", recon="指数每半年审核成分"),
    dict(code="SMH", name="半导体ETF", cat="行业", tier=1, flags=["hv"], alts=["SOXX"],
         index="MVIS US Listed Semiconductor 25", recon="每年 3 月、9 月审核成分（半导体收入≥50%才入选），每季度再平衡，单只上限 20%"),
    dict(code="XLF", name="金融ETF", cat="行业", tier=1, flags=[], alts=["VFH"],
         index="Financial Select Sector（标普500金融成分）", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="XLV", name="医疗保健ETF", cat="行业", tier=1, flags=[], alts=["VHT"],
         index="Health Care Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="XLE", name="能源ETF", cat="行业", tier=1, flags=["div"], alts=["VDE"],
         index="Energy Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="XLY", name="可选消费ETF", cat="行业", tier=1, flags=[], alts=["VCR"],
         index="Consumer Discretionary Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    # ---- 第二档：扩到 20 只 ----
    dict(code="QQQ", name="纳指100ETF", cat="宽基", tier=2, flags=[], alts=["QQQM"],
         index="Nasdaq-100", recon="每年 12 月重构（按市值取前 100 家非金融公司），每季度再平衡"),
    dict(code="TLT", name="20年+美债ETF", cat="债券", tier=2, flags=[], alts=["VGLT", "SPTL"],
         index="ICE U.S. Treasury 20+ Year", recon="每月再平衡，剩余期限不足 20 年的国债移出"),
    dict(code="SLV", name="白银ETF", cat="商品", tier=2, flags=["hv"], alts=["SIVR"],
         index="伦敦银价（实物白银）", recon="实物持有，无成分调整"),
    dict(code="EWJ", name="日本ETF", cat="海外", tier=2, flags=["fx"], alts=["BBJP"],
         index="MSCI Japan", recon="MSCI 每季度审核（2、5、8、11 月）"),
    dict(code="EWG", name="德国ETF", cat="海外", tier=2, flags=["fx"], alts=[],
         index="MSCI Germany", recon="MSCI 每季度审核（2、5、8、11 月）"),
    dict(code="XLI", name="工业ETF", cat="行业", tier=2, flags=[], alts=["VIS"],
         index="Industrial Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="XLU", name="公用事业ETF", cat="行业", tier=2, flags=["div"], alts=["VPU"],
         index="Utilities Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="IGV", name="软件ETF", cat="行业", tier=2, flags=[], alts=[],
         index="S&P North American Expanded Technology Software", recon="规则化指数，定期审核成分"),
    dict(code="XBI", name="生物科技ETF", cat="行业", tier=2, flags=["hv"], alts=["IBB"],
         index="S&P Biotechnology Select Industry（等权）", recon="每季度再平衡，等权重，小公司也有话语权"),
    dict(code="ITA", name="军工航天ETF", cat="行业", tier=2, flags=[], alts=["XAR"],
         index="Dow Jones U.S. Select Aerospace & Defense", recon="规则化指数，每季度再平衡"),
    # ---- 第三档：扩到 30 只（上限） ----
    dict(code="PDBC", name="综合商品ETF", cat="商品", tier=3, flags=["fut"], alts=["DBC"],
         index="主动管理的多品种商品期货（不发 K-1）", recon="按展期收益优化选合约，替代 USO/DBC 等 K-1 产品"),
    dict(code="GDX", name="金矿股ETF", cat="行业", tier=3, flags=["hv"], alts=["RING"],
         index="MarketVector Global Gold Miners", recon="规则化指数，定期审核成分"),
    dict(code="INDA", name="印度ETF", cat="海外", tier=3, flags=["fx"], alts=["EPI"],
         index="MSCI India", recon="MSCI 每季度审核（2、5、8、11 月）"),
    dict(code="EWY", name="韩国ETF", cat="海外", tier=3, flags=["fx", "hv"], alts=[],
         index="MSCI Korea 25/50", recon="MSCI 每季度审核；单一成分有 25% 上限"),
    dict(code="XLP", name="必需消费ETF", cat="行业", tier=3, flags=["div"], alts=["VDC"],
         index="Consumer Staples Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="XLC", name="通信服务ETF", cat="行业", tier=3, flags=[], alts=["VOX"],
         index="Communication Services Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="XLRE", name="房地产ETF", cat="行业", tier=3, flags=["div"], alts=["VNQ"],
         index="Real Estate Select Sector", recon="跟随标普500成分增删，每季度再平衡"),
    dict(code="KRE", name="地区银行ETF", cat="行业", tier=3, flags=["hv"], alts=[],
         index="S&P Regional Banks Select Industry", recon="规则化指数，每季度再平衡"),
    dict(code="URA", name="铀与核电ETF", cat="行业", tier=3, flags=["hv"], alts=["NLR"],
         index="Solactive Global Uranium & Nuclear Components", recon="规则化指数，定期审核成分"),
    dict(code="IBIT", name="比特币ETF", cat="加密", tier=3, flags=["hv", "gap"], alts=["FBTC"],
         index="比特币现货（实物持有）", recon="实物持有，无成分调整"),
]

DEFAULT_TIER_SIZE = 30

# RS（相对强弱）的比较基准；不在所选档位时也单独拉取，只做基准不进报告
BENCHMARK = dict(code="SPY", name="标普500ETF")
# 市场温度用的恐慌指数（只拉数据，不进池子）
VIX_CODE = "^VIX"

CAT_ORDER = ["宽基", "小盘", "红利", "债券", "商品", "加密", "海外", "行业"]

# ---------------------------------------------------------------------------
# 流动性门槛（pool_audit.py 用）。低于门槛的会在体检报告里标红，建议换候选
# ---------------------------------------------------------------------------
MIN_AUM = 1e9                 # 规模至少 10 亿美元
MIN_DOLLAR_VOL = 30e6         # 近 3 个月日均成交额至少 3000 万美元
MAX_SPREAD = 0.0010           # 买卖价差不超过 0.10%
SWAP_RATIO = 1.5              # 候选的日均成交额和规模都超过现任 1.5 倍，才建议换

# ---------------------------------------------------------------------------
# 指标参数
# ---------------------------------------------------------------------------
RSI_N = 14
RSI_LEVELS = (30, 20, 10)       # 左侧三档（按你的规则：跌破 30 / 20 / 10）
RSI_WATCH = 35                  # 30~35 为"接近超卖"观察区
RSI_OVERBOUGHT = (70, 80)       # 高抛两档
RSI2_OVERSOLD = 10              # 辅助：RSI(2) < 10 且在 200 日线上方 = 短线超卖（Connors 的经典规则），只进观察名单
# 市场温度 -> 总仓位上限（%）。日报展示和模拟盘共用同一张表：越冷越敢买，越热越收
TEMP_CAP = {"冰点": 100, "偏冷": 90, "中性": 80, "偏热": 65, "过热": 50}

# 美股规律：低波动 ETF（SPY、XLP 这类）一年也难得跌破 RSI 20，跌破 30 本身就很少见。
# 所以按波动分组，三档的分批比例不同：低波动组把子弹集中在第一档，高波动组留到深处。
VOL_GROUP_ATR = (1.2, 2.5)      # 近一年 ATR% 中位数 <1.2% 为低波动组，>2.5% 为高波动组
LEFT_TRANCHES = {               # 破30 / 破20 / 破10 各买多少（占该只上限的比例，累计为 1）
    "low": (0.5, 0.3, 0.2),
    "mid": (0.3, 0.3, 0.4),
    "high": (0.2, 0.3, 0.5),
}
GROUP_CN = {"low": "低波动", "mid": "中波动", "high": "高波动"}

MA_FAST = (3, 5, 7)             # 右侧三线
MA_TREND = (5, 20, 60)          # 均线图形
MA_LONG = 200                   # 美股看 200 日线（牛熊分界），A 股习惯的是 250 日年线

VOL_RATIO_OK = 1.2              # 量比 >= 1.2 视为温和放量
VOL_RATIO_STRONG = 1.5          # 量比 >= 1.5 视为明显放量
RIGHT_MIN_DAYS = 2              # 三线同步向上至少连续 N 天
RIGHT_FRESH_DAYS = 3            # 启动后 N 天内算"可上车"，之后算趋势延续、不追

REVIEW_DAYS = 20                # 报告里回顾最近 N 个交易日发出过的信号

MACD = (12, 26, 9)
GC_EARLY, GC_MID = 3, 10        # 金叉 1~3 天初期，4~10 天中期，>10 天后期

ATR_N = 14
CHANDELIER_N, CHANDELIER_K = 22, 3.0   # 吊灯止盈线：22 日最高 - 3×ATR
STOP_ATR_K = 2.0                # 初始止损：收盘价 - 2×ATR
BIAS_N = 20
BIAS_HOT_ATR = 3.0              # 乖离 > 3 倍 ATR% 提示追高（按各自波动归一，SPY 约 3%，URA 约 9%）
HIGH_VOL_PCTL = 0.8             # ATR% 处于自身近一年 80% 分位以上 = 当前高波动
GAP_ATR = 1.5                   # 开盘跳空超过 1.5 倍 ATR 单独提示
RS_N = 20
RS_WEAK_FRAC = 2 / 3            # 右侧只跟强者：RS 排在池内后 1/3 的放量上涨只算"弱势反弹"，不跟（欧奈尔/利弗莫尔）
CONTRARIAN_CATS = ("宽基", "红利")   # 大盘偏冷（温度 < 40）时，这两类超卖不因 200 日线下方减半（巴菲特：别人恐惧我贪婪，但只对宽基）
CONTRARIAN_SCORE = 40
CORR_N, CORR_HIGH = 60, 0.80    # 60 日相关性 > 0.8 视为高度同向

# VIX 恐慌指数分档
VIX_LEVELS = ((13, "平静"), (20, "正常"), (30, "紧张"), (999, "恐慌"))

# ---------------------------------------------------------------------------
# 盘中成交量折算：美股成交呈 U 形，尾盘含收盘集合竞价，最后半小时约占全天两成以上。
# 下面是美东时间 -> 已成交量占全天比例的估计，运行一个月后用真实数据校准。
# ---------------------------------------------------------------------------
VOL_CURVE = [(9 * 60 + 30, 0.0), (10 * 60, 0.11), (10 * 60 + 30, 0.19), (11 * 60, 0.26),
             (12 * 60, 0.37), (13 * 60, 0.46), (14 * 60, 0.56), (15 * 60, 0.69),
             (15 * 60 + 30, 0.79), (15 * 60 + 59, 0.90), (16 * 60, 1.0)]


def vol_share(hm: int) -> float:
    """美东某时刻（距 0 点的分钟数）已成交量约占全天的比例。"""
    pts = VOL_CURVE
    if hm <= pts[0][0]:
        return 0.05
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if hm <= t1:
            return max(0.05, v0 + (v1 - v0) * (hm - t0) / max(t1 - t0, 1))
    return 1.0


# 两个运行时段（美东时间）
SESSION_WINDOWS = {
    "mid": (10 * 60 + 15, 12 * 60 + 30),   # 盘中：开盘后约 1 小时（北京时间 22:30 / 23:30）
    "close_after": 5,                      # 收盘：收盘后 5 分钟起都算（北京时间早上 4:30 / 5:30）
}

FWD_DAYS = 10                   # 历史回看：信号出现后 N 个交易日的表现

# ---------------------------------------------------------------------------
# 仓位纪律（展示为占总资金的百分比）
# ---------------------------------------------------------------------------
RISK_PER_TRADE = 0.01           # 单笔最多亏总资金的 1%
MAX_POS = 0.20                  # 日报建议：单只上限 20%
EVENT_CUT = 0.5                 # 未来 2 个交易日内有 FOMC / CPI / 非农，右侧新开仓减半

# ---------------------------------------------------------------------------
# 税务：中国税务居民持有美国本土 ETF，分红按中美税收协定一般预扣 10%（需在券商填 W-8BEN）。
# 程序用"税后复权价"：分红按 90% 再投入，回测收益更接近真实到手。不构成税务建议。
# ---------------------------------------------------------------------------
DIV_WITHHOLD = 0.10

# ---------------------------------------------------------------------------
# 模拟盘（sim.py）
# ---------------------------------------------------------------------------
SIM_CASH = 100_000              # 初始资金（美元）
SIM_MAX_POS = 0.50              # 单只 ETF 最多占总资产 50%
SIM_MAX_POS_HV = 0.25           # 带 hv 标记的高波动品种最多 25%
SIM_FEE = 0.0                   # 佣金：主流美股券商 ETF 零佣金
SIM_SELL_FEE = 0.00003          # 卖出时的监管费（SEC 费 + FINRA TAF），按 0.003% 保守估计
SIM_SLIP = {1: 0.0002, 2: 0.0002, 3: 0.0008}   # 单边滑点，按档位：三档里有价差较大的品种
SIM_LOT = 1                     # 美股最小 1 股（不用碎股，贴近多数券商的限价单）
SIM_MIN_ORDER = 500             # 低于 500 美元的单子不下
SIM_DUST = 0.03                 # 减半后剩余不到总资产 3% 的，直接清掉
SIM_BACKTEST_YEARS = 5          # 回测 5 年：要覆盖 2022 年股债双杀
SIM_BENCH_6040 = ("SPY", "TLT", 0.6)   # 第二条对比线：60% 股 + 40% 长债，每月再平衡

# ---------------------------------------------------------------------------
# 数据源顺序（前一个失败自动换下一个）
#   yfinance：一次批量下载全部代码，只拉增量，减少被 Yahoo 限频的机会
#   tiingo  ：需要免费 API key，放环境变量 TIINGO_KEY（GitHub Secrets）
#   stooq   ：免费日线 CSV，最后兜底
# ---------------------------------------------------------------------------
SOURCES = ["yfinance", "tiingo", "stooq"]
TIINGO_MAX_CALLS = 40           # 免费版每小时 50 次，留 10 次余量
REQUEST_TIMEOUT = 15
REQUEST_RETRIES = 2
REQUEST_PAUSE = (0.3, 0.8)
HISTORY_START = "2000-01-01"    # 首次建缓存时往前拉到这天


def pool_for(size: int):
    """按档位返回池子：10 -> tier1；20 -> tier1+2；30 -> 全部。"""
    max_tier = 1 if size <= 10 else 2 if size <= 20 else 3
    return [p for p in POOL if p["tier"] <= max_tier]


def tier_of(code: str) -> int:
    return next((p["tier"] for p in POOL if p["code"] == code), 3)
