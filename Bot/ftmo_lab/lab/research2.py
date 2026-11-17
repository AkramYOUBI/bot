# -*- coding: utf-8 -*-
"""Etape 2 : portefeuilles + grille de risque -> taux de reussite FTMO, delai, revenu finance."""
import itertools
import sys
import time

import numpy as np

import strategies as S
from portfolio import build, challenge, components, funded, summarize

IDX4 = ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur"]
SPEC = [
    ("gold", S.gold_breakout, {}, ["xauusd"]),                       # 0
    ("silver", S.gold_breakout, {}, ["xagusd"]),                     # 1
    ("ibs", S.ibs_mr, {}, IDX4),                                     # 2-5
    ("rsi2", S.rsi2_mr, {"sl": 2.0}, IDX4),                          # 6-9
    ("dbl7", S.double7, {}, ["usa30idxusd", "usa500idxusd", "xauusd"]),  # 10-12
    ("h1gold", S.h1_breakout, {}, ["xauusd"]),                       # 13
]
COMPS = components(SPEC)
GROUP = {"gold": [0], "silver": [1], "ibs": [2, 3, 4, 5], "rsi2": [6, 7, 8, 9], "dbl7": [10, 11, 12], "h1": [13]}


def vec(**g):
    r = np.zeros(len(COMPS))
    for k, v in g.items():
        r[GROUP[k]] = v
    return r


def show(tag, tl, tb, r, **kw):
    s = summarize(challenge(tl, tb, r, **kw))
    f, _ = funded(tl, tb, r * 0.5 if kw.get("half") else r)
    print(f"{tag:55s} pass {s['pass_pct']:5.1f}% fail {s['fail_pct']:5.1f}% | med {s['med_days']:5.0f}j "
          f"p75 {s['p75_days']:5.0f}j | <=90j {s['in90']:4.0f}% <=180j {s['in180']:4.0f}% || "
          f"finance {f['per_month']:+6.0f}$/m DD {f['dd_peak_pct']:4.1f}% st {f['status']}", flush=True)


if __name__ == "__main__":
    t0 = time.time()
    tl, tb = build(COMPS)
    print(f"build {time.time() - t0:.1f}s, trades {len(tb.sorted_rows)}")
    show("BASE GoldFTMO seul 1.5%", tl, tb, vec(gold=1.5))
    show("Gold 1.5 + silver 1.0", tl, tb, vec(gold=1.5, silver=1.0))
    for g, i, r2, d7 in itertools.product([1.5, 2.5], [0.75, 1.5], [0, 1.0], [0, 1.0]):
        show(f"gold {g} ibs {i} rsi2 {r2} dbl7 {d7}", tl, tb, vec(gold=g, ibs=i, rsi2=r2, dbl7=d7))
    print(f"total {time.time() - t0:.1f}s")
