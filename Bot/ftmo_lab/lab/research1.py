# -*- coding: utf-8 -*-
"""Etape 1 : edge brut de chaque strategie x instrument depuis 2020 (en R, couts inclus)."""
import sys
import numpy as np
import pandas as pd

from data import load
import strategies as S

IDX = ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur", "gbridxgbp", "jpnidxjpy"]
FX = ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy", "gbpjpy"]
MET = ["xauusd", "xagusd"]

TESTS = {
    "gold_brk": (S.gold_breakout, {}, MET),
    "gold_brk_both": (S.gold_breakout, {"both": True}, MET + IDX),
    "rsi2": (S.rsi2_mr, {}, IDX + MET),
    "rsi2_t5": (S.rsi2_mr, {"th": 5}, IDX + MET),
    "rsi2_sl2": (S.rsi2_mr, {"sl": 2.0}, IDX),
    "down3": (S.down_days, {"n": 3}, IDX + MET),
    "donch55": (S.donchian, {}, FX + MET + IDX),
    "donch20_10": (S.donchian, {"en": 20, "ex": 10}, FX + MET + IDX),
    "ibs": (S.ibs_mr, {}, IDX + MET),
    "ibs_notrend": (S.ibs_mr, {"trend": 0}, IDX + MET),
    "ibs_x1d": (S.ibs_mr, {"exit_prevhigh": False}, IDX),
    "ibs_x08": (S.ibs_mr, {"exit_prevhigh": False, "exit_ibs": 0.8}, IDX),
    "dbl7": (S.double7, {}, IDX + MET),
    "tom": (S.tom, {}, IDX + MET),
    "tom_2_2": (S.tom, {"before": 2, "after": 2}, IDX),
    "rsi2_sl2_x3": (S.rsi2_mr, {"sl": 2.0, "exit_ma": 3}, IDX),
    "rsi2_t20": (S.rsi2_mr, {"th": 20, "sl": 2.0}, IDX),
    "h1mr": (S.h1_mr, {}, ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur", "xauusd"]),
    "h1mr_t10": (S.h1_mr, {"th": 10}, ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur", "xauusd"]),
    "h1mr_sess": (S.h1_mr, {"hours": set(range(9, 23))}, ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur", "xauusd"]),
    "h1mr_sl2": (S.h1_mr, {"sl": 2.0, "maxh": 12}, ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur", "xauusd"]),
    "x_gold_brk": (S.gold_breakout, {}, ["btcusd", "ethusd", "lightcmdusd", "brentcmdusd"]),
    "x_brk_both": (S.gold_breakout, {"both": True}, ["btcusd", "ethusd", "lightcmdusd", "brentcmdusd"]),
    "x_donch55": (S.donchian, {}, ["btcusd", "ethusd", "lightcmdusd", "brentcmdusd"]),
    "x_donch20": (S.donchian, {"en": 20, "ex": 10}, ["btcusd", "ethusd", "lightcmdusd", "brentcmdusd"]),
    "x_donch20L": (S.donchian, {"en": 20, "ex": 10, "both": False}, ["btcusd", "ethusd"]),
    "x_ibs": (S.ibs_mr, {}, ["fraidxeur", "eusidxeur", "ausidxaud", "hkgidxhkd", "espidxeur", "btcusd", "lightcmdusd"]),
    "x_rsi2": (S.rsi2_mr, {"sl": 2.0}, ["fraidxeur", "eusidxeur", "ausidxaud", "hkgidxhkd", "espidxeur", "btcusd", "lightcmdusd"]),
    "s_rsi2short": (S.rsi2_mr, {"sl": 2.0, "short": True, "th": 10}, ["usa500idxusd", "usatechidxusd", "usa30idxusd", "deuidxeur"]),
    "cryT3": (S.donchian, {"en": 20, "ex": 10, "both": False, "trail": 3.0}, ["btcusd", "ethusd"]),
    "cryT2": (S.donchian, {"en": 20, "ex": 10, "both": False, "trail": 2.0}, ["btcusd", "ethusd"]),
    "cryTP3": (S.donchian, {"en": 20, "ex": 10, "both": False, "tp": 3.0}, ["btcusd", "ethusd"]),
    "cryE": (S.donchian, {"en": 20, "ex": 10, "both": False, "trail": 3.0, "ema_n": 50}, ["btcusd", "ethusd"]),
    "c_brk": (S.gold_breakout, {}, ["xagusd", "xptcmdusd", "xpdcmdusd", "gascmdusd", "cocoacmdusd", "coffeecmdusx", "cottoncmdusx", "soybeancmdusx", "sugarcmdusd", "coppercmdusd"]),
    "c_brk_both": (S.gold_breakout, {"both": True}, ["xptcmdusd", "xpdcmdusd", "gascmdusd", "cocoacmdusd", "coffeecmdusx", "cottoncmdusx", "soybeancmdusx", "sugarcmdusd", "coppercmdusd"]),
    "h1brk_long": (S.h1_breakout, {}, MET + IDX),
}


def stats(trades, since="2020-01-01"):
    rows = [(t[2], t[0][3]) for t in trades if t[2] >= pd.Timestamp(since)]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["d", "r"])
    eq = df["r"].cumsum()
    dd = (eq.cummax().clip(lower=0) - eq).max()
    yrs = df.groupby(df["d"].dt.year)["r"].sum()
    span = (pd.Timestamp("2026-11-17") - pd.Timestamp(since)).days / 365.25
    return dict(n=len(df), wr=(df["r"] > 0).mean() * 100, avg=df["r"].mean(), tot=df["r"].sum(),
                ddR=dd, peryr=len(df) / span, yrs=" ".join(f"{y % 100}:{v:+.1f}" for y, v in yrs.items()),
                neg_years=int((yrs < 0).sum()))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0].startswith("delay="):
        S.DELAY["h"] = int(args.pop(0)[6:])
    sel = args or list(TESTS)
    for name in sel:
        fn, kw, syms = TESTS[name]
        print(f"\n=== {name} {kw}")
        for s in syms:
            st = stats(fn(load(s), **kw))
            if st:
                print(f"  {s:14s} n={st['n']:4d} ({st['peryr']:5.1f}/an) WR {st['wr']:3.0f}% avg {st['avg']:+.2f}R "
                      f"tot {st['tot']:+6.1f}R ddR {st['ddR']:5.1f} | {st['yrs']}")
