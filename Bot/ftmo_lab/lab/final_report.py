# -*- coding: utf-8 -*-
"""Rapport final FTMOPortfolio : challenge 2-Step + compte finance + stress tests + comparaison GoldFTMO."""
import sys

import numpy as np
import pandas as pd

import data
import portfolio
import strategies as S
from portfolio import build, challenge, components, funded, summarize
from research5 import BASE, COMPS, W

K_CHAL, K_FUND = 2.5, 0.75
OPT = dict(guard=3.5, max_open=8.0, dd_scale=0.1)
L = []


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    L.append(s)


def bloc(tag, tl, tb, base=BASE):
    df = challenge(tl, tb, base * K_CHAL, **OPT)
    s = summarize(df)
    f, eq = funded(tl, tb, base * K_FUND, **OPT)
    p(f"[{tag}] CHALLENGE x{K_CHAL}: reussite {s['pass_pct']:.1f}% | echec {s['fail_pct']:.1f}% | "
      f"delai median {s['med_days']:.0f}j | 75% en {s['p75_days']:.0f}j | 90% en {s['p90_days']:.0f}j | "
      f"<=3 mois {s['in90']:.0f}% | <=6 mois {s['in180']:.0f}%")
    p(f"[{tag}] FINANCE  x{K_FUND}: {f['per_month']:+.0f}$/mois moyen (median {f['med_month']:+.0f}) | mois positifs "
      f"{f['pos_months']:.0f}% | pire mois {f['worst_month']:+.0f}$ | DD pic {f['dd_peak_pct']:.1f}% | "
      f"equity min {f['min_eq']:.0f}$ | pire perte jour {f['max_daily_loss']:.0f}$ | statut {'OK' if f['status'] >= 0 else 'ECHEC'}")
    p(f"[{tag}]   par annee: {f['years']}")
    return df, f, eq


if __name__ == "__main__":
    S.DELAY["h"] = 2
    portfolio.REF_EQ[0] = 0  # regle FTMO : perte jour depuis le solde de debut de journee
    p("RAPPORT FTMOPortfolio — FTMO 100k 2-Step (Phase 1 +10 %, Phase 2 +5 %, -5 %/jour, -10 % total, 4 jours min)")
    p("Donnees: Dukascopy H1 bid+ask 2019-2026 | execution ask/bid reelle + commission + swap | conflit SL/TP -> SL")
    p("Departs de challenge: chaque semaine du 2020-01-06 au 2025-11-01 (~300 challenges simules)")
    p("Risque par trade (% du capital initial) en CHALLENGE / FINANCE :")
    for c, b in zip(COMPS, BASE):
        p(f"   {c[0]:24s} {b * K_CHAL:4.2f}% / {b * K_FUND:4.2f}%")
    p("")
    tl, tb = build(COMPS)
    p(f"Trades 2019-2026: {len(tb.sorted_rows)}")
    df, f, eq = bloc("BASE", tl, tb)
    df["y"] = df.start.dt.year
    p(df.groupby("y").agg(n=("p2", "size"), reussi_pct=("p2", lambda x: (x == 1).mean() * 100),
                          echec_pct=("p1", lambda x: (x == -1).mean() * 100), jours_median=("days", "median"),
                          phase1_med=("d1", "median"), phase2_med=("d2", "median")).round(0).to_string())
    eq.to_csv("/out/equity_finance.csv")
    df.to_csv("/out/challenges.csv", index=False)

    p("\n--- Regle jour ultra-prudente (ref = max(solde, equity) a minuit) ---")
    portfolio.REF_EQ[0] = 1
    bloc("PRUDENT", tl, tb)
    portfolio.REF_EQ[0] = 0

    p("\n--- STRESS: couts x2 + swaps x2 ---")
    for k in list(data.EXTRA):
        data.EXTRA[k] *= 2
    for k in list(data.COST):
        data.COST[k] *= 2
    data.SWAP_YEAR = 0.10
    data.SWAP.update({"btcusd": 0.40, "ethusd": 0.40})
    data.load.cache_clear()
    tl2, tb2 = build(COMPS)
    bloc("COUTSx2", tl2, tb2)
    for k in list(data.EXTRA):
        data.EXTRA[k] /= 2
    for k in list(data.COST):
        data.COST[k] /= 2
    data.SWAP_YEAR = 0.05
    data.SWAP.update({"btcusd": 0.20, "ethusd": 0.20})
    data.load.cache_clear()

    p("\n--- STRESS: entree des la reouverture (delai 0h) ---")
    S.DELAY["h"] = 0
    tl3, tb3 = build(COMPS)
    bloc("DELAI0", tl3, tb3)
    S.DELAY["h"] = 2

    p("\n--- STRESS: sans crypto (si BTC/ETH indisponibles) ---")
    base_nc = np.array([0.0 if c[0].startswith("cry") else b for c, b in zip(COMPS, BASE)])
    bloc("SANS_CRYPTO", tl, tb, base_nc)

    p("\n--- REFERENCE: GoldFTMO actuel seul (or cassure D1, 1.5 %) meme moteur ---")
    ref = [c for c in COMPS if c[0] == "brk:xauusd"]
    tlr, tbr = build(ref)
    s = summarize(challenge(tlr, tbr, np.array([1.5]), **OPT))
    fr, _ = funded(tlr, tbr, np.array([1.5]), **OPT)
    p(f"[GoldFTMO] reussite {s['pass_pct']:.1f}% | echec {s['fail_pct']:.1f}% | delai median {s['med_days']:.0f}j | "
      f"90% en {s['p90_days']:.0f}j | finance {fr['per_month']:+.0f}$/mois DD {fr['dd_peak_pct']:.1f}%")
    open("/out/rapport_ftmo_portfolio.txt", "w").write("\n".join(L) + "\n")
