import itertools, sys
import numpy as np, pandas as pd
import portfolio, strategies as S
from portfolio import build, challenge, components, funded, summarize
from research1 import stats
from data import load
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
G = ["xauusd"]
SPEC = [
    ("brk20", S.gold_breakout, {"rr": 3.0}, G),
    ("brk55", S.gold_breakout, {"en": 55, "ex": 20, "maxd": 30}, G),
    ("d7", S.double7, {}, G),
    ("mom", S.tsmom_w, {"look": 60}, G),
]
for n, fn, kw, s in SPEC:
    st = stats(fn(load("xauusd"), **kw)); print(n, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in st.items()})
C = components(SPEC)
tl, tb = build(C)
OPT = dict(guard=3.5, max_open=8.0, dd_scale=0.1)
def line(tag, w, k):
    s = summarize(challenge(tl, tb, np.array(w) * k, **OPT))
    print(f"{tag:34s} k{k}: pass {s['pass_pct']:5.1f}% fail {s['fail_pct']:4.1f}% | med {s['med_days']:4.0f}j p75 {s['p75_days']:4.0f}j p90 {s['p90_days']:4.0f}j | <=180j {s['in180']:3.0f}%", flush=True)
for w in [(1, 0, 0, 0), (1, 1, 0, 0), (1, 1, 0.6, 0), (1, 1, 0.6, 0.5), (1, 0.7, 0.8, 0.6), (1, 1, 1, 1)]:
    for k in [1.5, 2.0, 2.5, 3.0]:
        line(str(w), w, k)
for w in [(1, 1, 0.6, 0.5), (1, 0.7, 0.8, 0.6)]:
    for k in [0.75, 1.0, 1.5, 2.0]:
        f, _ = funded(tl, tb, np.array(w) * k, **OPT)
        print(f"FINANCE {w} k{k}: {f['per_month']:+.0f}$/m (med {f['med_month']:+.0f}) | mois+ {f['pos_months']:.0f}% | pire mois {f['worst_month']:+.0f} | DD pic {f['dd_peak_pct']:.1f}% | eq min {f['min_eq']:.0f} | jour max {f['max_daily_loss']:.0f} | st {f['status']} | {f['years']}")
