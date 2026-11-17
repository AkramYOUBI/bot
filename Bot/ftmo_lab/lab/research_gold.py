# Recherche OR SEUL : variantes, Sharpe journalier, correlations
import numpy as np, pandas as pd, sys
import strategies as S
from portfolio import build, components, run, INIT
from research1 import stats
S.DELAY["h"] = 2
G = ["xauusd"]
SPEC = [
    ("brk20", S.gold_breakout, {}, G),
    ("brk10", S.gold_breakout, {"en": 10, "ex": 5, "maxd": 8}, G),
    ("brk55", S.gold_breakout, {"en": 55, "ex": 20, "maxd": 30}, G),
    ("brk20_rr3", S.gold_breakout, {"rr": 3.0}, G),
    ("brk20_short", S.gold_breakout, {"both": True}, G),
    ("d7", S.double7, {}, G),
    ("d5", S.double7, {"n": 5}, G),
    ("d10", S.double7, {"n": 10}, G),
    ("d7_t100", S.double7, {"trend": 100}, G),
    ("rsi2_t5", S.rsi2_mr, {"th": 5}, G),
    ("rsi2_t15_sl2", S.rsi2_mr, {"th": 15, "sl": 2.0}, G),
    ("down3", S.down_days, {"n": 3}, G),
    ("down2_ma5", S.down_days, {"n": 2, "exit_ma": 5}, G),
    ("ibs01", S.ibs_mr, {"lo": 0.1}, G),
    ("tom", S.tom, {}, G),
    ("tsmom60", S.tsmom, {"look": 60}, G),
    ("tsmom20", S.tsmom, {"look": 20}, G),
    ("tsmom120_ma50", S.tsmom, {"look": 120, "ma": 50}, G),
    ("asia", S.asian_breakout, {}, G),
    ("asia_long", S.asian_breakout, {"both": False}, G),
    ("asia_tr", S.asian_breakout, {"dtrend": 50}, G),
    ("asia_rr2", S.asian_breakout, {"rr": 2.0, "dtrend": 50}, G),
    ("h1brk", S.h1_breakout, {}, G),
    ("h1brk_ema200", S.h1_breakout, {"ema_n": 200}, G),
    ("h1brk_e72", S.h1_breakout, {"en": 72, "ex": 36, "ema_n": 200}, G),
    ("h1brk_sess", S.h1_breakout, {"ema_n": 200, "hours": set(range(9, 19))}, G),
]
C = components(SPEC)
tl, tb = build(C)
g0 = tl.gi_of_date("2020-01-01"); Gn = len(tl.t)
cols, rows = {}, []
for i, c in enumerate(C):
    r = np.zeros(len(C)); r[i] = 1.0
    *_, daily = run(tl, tb, r, g0, Gn, 0.0, guard=50, max_open=100, min_days=0, rec=True)
    s = pd.Series(daily).ffill().fillna(INIT)
    cols[c[0]] = s.diff().fillna(s.iloc[0] - INIT) / 1000.0
    st = stats(c[1](S.load(c[3]) if False else __import__("data").load(c[3]), **c[2]))
    rows.append((c[0], st))
df = pd.DataFrame(cols)
df.index = tl.days[tl.day_codes[g0]: tl.day_codes[g0] + len(df)]
df = df[df.index.weekday < 5]
sh = df.mean() / df.std() * np.sqrt(252)
sh1 = df[:"2022"].mean() / df[:"2022"].std() * np.sqrt(252)
sh2 = df["2023":].mean() / df["2023":].std() * np.sqrt(252)
for name, st in rows:
    print(f"{name:16s} Sharpe {sh[name]:5.2f} (20-22 {sh1[name]:5.2f} | 23-26 {sh2[name]:5.2f}) n={st['n']:4d} WR {st['wr']:3.0f}% "
          f"avg {st['avg']:+.2f}R ddR {st['ddR']:4.1f} | {st['yrs']}")
df.to_pickle("/out/gold_daily.pkl")
good = [n for n in sh.index if sh[n] > 0.4]
print(df[good].corr().round(2).to_string())
