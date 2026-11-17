# Sharpe + correlations des composants journaliers (MTM quotidien, 1 % de risque, sans garde-fous)
import numpy as np, pandas as pd
import strategies as S
from portfolio import build, components, run, INIT
S.DELAY["h"] = 2
IDX = ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur", "gbridxgbp", "jpnidxjpy"]
SPEC = [
    ("gold", S.gold_breakout, {}, ["xauusd", "xagusd", "lightcmdusd", "brentcmdusd", "btcusd", "ethusd"]),
    ("cryL", S.donchian, {"en": 20, "ex": 10, "both": False}, ["btcusd", "ethusd"]),
    ("cry55", S.donchian, {}, ["btcusd", "ethusd"]),
    ("rsi2s", S.rsi2_mr, {"sl": 2.0, "short": True}, ["usa500idxusd"]),
    ("goldboth", S.gold_breakout, {"both": True}, ["xauusd"]),
    ("donch55", S.donchian, {}, ["xauusd", "usa500idxusd", "usatechidxusd", "jpnidxjpy"]),
    ("ibs", S.ibs_mr, {}, IDX + ["xauusd"]),
    ("ibsx08", S.ibs_mr, {"exit_prevhigh": False, "exit_ibs": 0.8}, IDX[:4]),
    ("rsi2", S.rsi2_mr, {"sl": 2.0}, IDX),
    ("rsi2t20", S.rsi2_mr, {"th": 20, "sl": 2.0}, IDX[:4]),
    ("dbl7", S.double7, {}, IDX[:4] + ["xauusd"]),
    ("down3", S.down_days, {}, IDX[:4]),
    ("tom", S.tom, {}, IDX[:4]),
]
C = components(SPEC)
tl, tb = build(C)
g0 = tl.gi_of_date("2020-01-01"); G = len(tl.t)
cols = {}
for i, c in enumerate(C):
    r = np.zeros(len(C)); r[i] = 1.0
    st, *_, daily = run(tl, tb, r, g0, G, 0.0, guard=50, max_open=100, min_days=0, rec=True)
    s = pd.Series(daily).ffill().fillna(INIT)
    cols[c[0]] = s.diff().fillna(s.iloc[0] - INIT) / 1000.0  # en R
df = pd.DataFrame(cols)
df.index = tl.days[tl.day_codes[g0]: tl.day_codes[g0] + len(df)]
df = df[df.index.weekday < 5]
sh = df.mean() / df.std() * np.sqrt(252)
yr = df.sum() / (len(df) / 252)
print(pd.DataFrame({"sharpe": sh.round(2), "R_par_an": yr.round(1)}).sort_values("sharpe", ascending=False).to_string())
df.to_pickle("/out/comp_daily.pkl")
import sys; sys.exit(0)
good = sh[sh > 0.5].index
print("\ncorr (Sharpe>0.5):"); print(df[good].corr().round(2).to_string())
