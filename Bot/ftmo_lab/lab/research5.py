# -*- coding: utf-8 -*-
"""Etape 5 : portefeuille final candidat -> grille de risque sur simulation FTMO complete."""
import itertools
import sys

import numpy as np

import strategies as S
from portfolio import build, challenge, components, funded, summarize

S.DELAY["h"] = 2
BRK = dict(en=20, ex=10, sl=1.8, rr=2.0, ema_n=50, maxd=15, cap=2.2)
SPEC = [
    # (nom, fonction, params, symboles)  -> poids relatifs dans W
    ("brk", S.gold_breakout, BRK, ["xauusd", "lightcmdusd", "brentcmdusd"]),
    ("cry", S.donchian, {"en": 20, "ex": 10, "both": False, "tp": 3.0}, ["btcusd", "ethusd"]),
    ("d7", S.double7, {}, ["xauusd", "usa30idxusd"]),
    ("ibs", S.ibs_mr, {}, ["usatechidxusd", "usa500idxusd", "usa30idxusd", "deuidxeur"]),
    ("rsi2", S.rsi2_mr, {"sl": 2.0}, ["usa500idxusd"]),
    ("rsi2b", S.rsi2_mr, {"sl": 2.0, "th": 20}, ["usatechidxusd"]),
]
COMPS = components(SPEC)
W = {"brk:xauusd": 1.0, "brk:lightcmdusd": 0.7, "brk:brentcmdusd": 0.3,
     "cry:btcusd": 0.4, "cry:ethusd": 0.4, "d7:xauusd": 0.5, "d7:usa30idxusd": 0.4,
     "ibs:usatechidxusd": 0.4, "ibs:usa500idxusd": 0.4, "ibs:usa30idxusd": 0.4, "ibs:deuidxeur": 0.4,
     "rsi2:usa500idxusd": 0.6, "rsi2b:usatechidxusd": 0.6}
BASE = np.array([W[c[0]] for c in COMPS])


def line(tag, s, f):
    return (f"{tag:48s} pass {s['pass_pct']:5.1f}% fail {s['fail_pct']:4.1f}% | med {s['med_days']:4.0f}j "
            f"p75 {s['p75_days']:4.0f}j p90 {s['p90_days']:4.0f}j | <=90j {s['in90']:3.0f}% <=180j {s['in180']:3.0f}%"
            + (f" || fin {f['per_month']:+5.0f}$/m DDpk {f['dd_peak_pct']:4.1f}% min {f['min_eq']:6.0f} st {f['status']}" if f else ""))


if __name__ == "__main__":
    import portfolio
    if "ftmo" in sys.argv:
        portfolio.REF_EQ[0] = 0
        sys.argv.remove("ftmo")
    tl, tb = build(COMPS)
    print("trades:", len(tb.sorted_rows))
    mode = sys.argv[1] if len(sys.argv) > 1 else "grid"
    if mode == "grid":
        for k, dds, guard, mo in itertools.product([1.0, 1.5, 2.0, 2.5, 3.0], [0.0, 0.06, 0.1], [3.5], [8.0]):
            r = BASE * k
            s = summarize(challenge(tl, tb, r, guard=guard, max_open=mo, dd_scale=dds))
            f, _ = funded(tl, tb, r, guard=guard, max_open=mo, dd_scale=dds)
            print(line(f"k{k} dds{dds} guard{guard} maxopen{mo}", s, f), flush=True)
    elif mode == "p2":
        for k, k2 in itertools.product([1.5, 2.0, 2.5], [0.6, 1.0]):
            s = summarize(challenge(tl, tb, BASE * k, BASE * k * k2, guard=3.5, max_open=8.0, dd_scale=0.08))
            print(line(f"k{k} phase2 x{k2}", s, None), flush=True)
    elif mode == "boost":
        for k, up, k2 in itertools.product([2.0, 2.5], [0.0, 0.3, 0.6], [1.0, 0.7]):
            portfolio.UP[0] = up
            df = challenge(tl, tb, BASE * k, BASE * k * k2, guard=3.5, max_open=8.0, dd_scale=0.1)
            s = summarize(df)
            print(line(f"k{k} up{up} p2x{k2}", s, None), flush=True)
        portfolio.UP[0] = 0.0
    elif mode == "years":
        df = challenge(tl, tb, BASE * 2.5, guard=3.5, max_open=8.0, dd_scale=0.1)
        df["y"] = df.start.dt.year
        print(df.groupby("y").agg(n=("p2", "size"), reussi=("p2", lambda x: (x == 1).mean() * 100),
              echec=("p1", lambda x: (x == -1).mean() * 100), jours_med=("days", "median"),
              p1_med=("d1", "median"), p2_med=("d2", "median")).round(0).to_string())
    elif mode == "funded":
        for k in [0.5, 0.75, 1.0, 1.25]:
            f, s = funded(tl, tb, BASE * k, guard=3.5, max_open=8.0, dd_scale=0.08)
            print(f"finance k{k}: {f['per_month']:+.0f}$/mois (median {f['med_month']:+.0f}) | mois+ {f['pos_months']:.0f}% "
                  f"| pire mois {f['worst_month']:+.0f} | DD pic {f['dd_peak_pct']:.1f}% | equity min {f['min_eq']:.0f} "
                  f"| perte jour max {f['max_daily_loss']:.0f} | annees {f['years']}")
