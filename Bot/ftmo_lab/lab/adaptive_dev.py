# DEVELOPPEMENT sur 2008-2015 UNIQUEMENT (2016-2026 reste cache)
import sys, itertools
import numpy as np, pandas as pd
import strategies as S
from data import load
S.DELAY["h"] = 2
I = load("xaulong")
DEV = ("2008-01-01", "2015-12-31")
def st(tr, a, b):
    rows = [(t[2], t[0][3], t[1], t[3]) for t in tr if pd.Timestamp(a) <= t[2] <= pd.Timestamp(b)]
    if not rows: return "aucun trade"
    df = pd.DataFrame(rows, columns=["d", "r", "side", "reg"])
    eq = df.r.cumsum(); dd = (eq.cummax().clip(lower=0) - eq).max()
    yr = df.groupby(df.d.dt.year).r.sum().round(1).to_dict()
    sides = df.groupby("side").r.agg(["size", "sum"]).round(1).to_dict("index")
    return f"n={len(df):3d} WR {(df.r>0).mean()*100:3.0f}% moy {df.r.mean():+.2f}R tot {df.r.sum():+5.1f}R DD {dd:4.1f}R | achat/vente {sides} | {yr}"
if __name__ != "__main__": grid = {}
else: grid = {
  "pullback": [dict(rsi_pb=p, rr=r, sr_tol=t) for p, r, t in itertools.product([35, 40, 45], [1.5, 2.0, 3.0], [0.3, 0.5])],
  "breakout": [dict(brk_en=e, brk_ex=x, brk_rr=r) for e, x, r in itertools.product([20, 55], [10, 20], [2.0, 3.0])],
  "range": [dict(rsi_rng=q, sr_tol=t, look_sr=lk) for q, t, lk in itertools.product([30, 35, 40], [0.3, 0.5], [60, 120])],
}
for setup, cfgs in grid.items():
    print(f"\n=== {setup} (DEV 2008-2015)")
    for kw in cfgs:
        print(f"  {str(kw):55s} {st(S.adaptive(I, setup=setup, **kw), *DEV)}")
