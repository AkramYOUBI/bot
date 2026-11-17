# -*- coding: utf-8 -*-
"""Portefeuille multi-strategies + evaluation challenge FTMO 2-Step sur departs glissants."""
from __future__ import annotations

import numpy as np
import pandas as pd

import strategies as S
from data import load
from engine import Timeline, TradeBook, account

INIT = 100_000.0
REF_EQ = [1]
UP = [0.0]  # 1 = ref jour = max(balance, equity) (prudent) ; 0 = balance (regle FTMO)

# composant = (nom, fonction, kwargs, symbole)
def components(spec):
    return [(f"{n}:{s}", fn, kw, s) for (n, fn, kw, syms) in spec for s in syms]


def build(comps):
    insts = [load(c[3]) for c in comps]
    tl = Timeline(list({I.name: I for I in insts}.values()))
    tb = TradeBook(tl)
    for sid, (name, fn, kw, sym) in enumerate(comps):
        I = load(sym)
        for res, side, d in fn(I, **kw):
            tb.add(sid, I, res, side, name)
    tb.pack()
    return tl, tb


def run(tl, tb, risk, g0, g1, target, guard=4.0, max_open=6.0, min_days=4, dd_scale=0.0, rec=False):
    ref_eq = REF_EQ[0]
    gs, ge, sid, fin, off, W, C = tb.packed
    return account(gs, ge, sid, fin, off, W, C, tl.day_codes, np.asarray(risk, float) / 100.0,
                   g0, g1, target, INIT, guard / 100.0, max_open / 100.0, min_days, dd_scale, rec, ref_eq, UP[0])


def challenge(tl, tb, risk1, risk2=None, start="2020-01-06", last_start="2025-11-01", step_days=7,
              guard=4.0, max_open=6.0, dd_scale=0.0):
    """Pour chaque depart : Phase 1 (+10 %) puis Phase 2 (+5 %) des le lendemain."""
    risk2 = risk1 if risk2 is None else risk2
    G = len(tl.t)
    out = []
    for d in pd.date_range(start, last_start, freq=f"{step_days}D"):
        g0 = tl.gi_of_date(d)
        st1, gst1, *_ = run(tl, tb, risk1, g0, G, 0.10, guard, max_open, 4, dd_scale)
        r = dict(start=d, p1=st1, d1=np.nan, p2=0, d2=np.nan, days=np.nan)
        if st1 == 1:
            r["d1"] = (tl.t[gst1] - tl.t[g0]) / 86400
            gn = tl.gi_of_date(pd.Timestamp(tl.idx[gst1].date()) + pd.Timedelta(days=1))
            st2, gst2, *_ = run(tl, tb, risk2, gn, G, 0.05, guard, max_open, 4, dd_scale)
            r["p2"] = st2
            if st2 == 1:
                r["d2"] = (tl.t[gst2] - tl.t[gn]) / 86400
                r["days"] = (tl.t[gst2] - tl.t[g0]) / 86400
        out.append(r)
    return pd.DataFrame(out)


def summarize(df):
    n = len(df)
    ok = df["p2"] == 1
    fail = (df["p1"] == -1) | (df["p2"] == -1)
    days = df.loc[ok, "days"]
    return dict(n=n, pass_pct=ok.mean() * 100, fail_pct=fail.mean() * 100,
                med_days=days.median() if len(days) else np.nan,
                p75_days=days.quantile(0.75) if len(days) else np.nan,
                p90_days=days.quantile(0.90) if len(days) else np.nan,
                in90=(ok & (df["days"] <= 90)).mean() * 100,
                in180=(ok & (df["days"] <= 180)).mean() * 100)


def funded(tl, tb, risk, start="2020-01-01", guard=4.0, max_open=6.0, dd_scale=0.0):
    g0 = tl.gi_of_date(start)
    st, gst, eq, mn, ntr, tdays, mdl, daily = run(tl, tb, risk, g0, len(tl.t), 0.0, guard, max_open, 0,
                                                  dd_scale, True)
    days = tl.days[tl.day_codes[g0]: tl.day_codes[g0] + len(daily)]
    s = pd.Series(daily, index=days).ffill().fillna(INIT)
    m = s.resample("ME").last()
    mp = m.diff().fillna(m.iloc[0] - INIT)
    dd_peak = ((s.cummax() - s) / INIT).max() * 100
    return dict(status=st, end_bal=eq, net=eq - INIT, per_month=mp.mean(), med_month=mp.median(),
                pos_months=(mp > 0).mean() * 100, worst_month=mp.min(), min_eq=mn, dd_peak_pct=dd_peak,
                max_daily_loss=mdl, trades=ntr, years=mp.groupby(mp.index.year).sum().round(0).to_dict()), s
