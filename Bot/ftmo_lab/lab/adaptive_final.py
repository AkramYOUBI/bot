import itertools
import numpy as np, pandas as pd
import portfolio, strategies as S
from portfolio import build, challenge, components, funded, summarize
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
X = ["xaulong"]
ADAPT = [("rbrk20", S.adaptive, {"setup": "breakout", "brk_en": 20, "brk_ex": 10, "brk_rr": 3.0}, X),
         ("rbrk55", S.adaptive, {"setup": "breakout", "brk_en": 55, "brk_ex": 20, "brk_rr": 2.0, "maxd": 30}, X),
         ("rmom", S.regime_mom, {"look": 60}, X)]
WA = np.array([1.0, 0.7, 0.6])
V13 = [("brk20", S.gold_breakout, {"rr": 3.0}, X), ("brk55", S.gold_breakout, {"en": 55, "ex": 20, "maxd": 30}, X),
       ("d7", S.double7, {}, X), ("mom", S.tsmom_w, {"look": 60}, X)]
WV = np.array([1.0, 0.7, 0.8, 0.6])
L = []
def p(s=""): print(s, flush=True); L.append(s)

def windows(eq, tag):
    s = eq[eq.index.weekday < 5]
    out = []
    for W, nm in ((21, "1 mois"), (63, "3 mois"), (126, "6 mois")):
        r = (s.shift(-W) - s).dropna()
        out.append(f"{nm}: positif {(r > 0).mean() * 100:3.0f}% | median {r.median():+6.0f}$ | pire {r.min():+6.0f}$")
    peak = s.cummax(); under = (s < peak - 1)
    runs, cur = [], 0
    for u in under:
        cur = cur + 1 if u else 0; runs.append(cur)
    p(f"  [{tag}] fenetres glissantes -> " + " || ".join(out) + f" || plus longue periode sous le sommet: {max(runs) / 21:.0f} mois")

def report(name, spec, W, K):
    C = components(spec); tl, tb = build(C)
    p(f"\n##### {name}")
    rows = [(r[8].split(':')[0], tl.days[tl.day_codes[r[0]]], r[5], r[7]) for r in tb.sorted_rows]
    df = pd.DataFrame(rows, columns=["c", "d", "r", "side"])
    df["y"] = df.d.dt.year
    pv = df.pivot_table(index="y", columns="c", values="r", aggfunc="sum").round(1)
    pv["ventes_R"] = df[df.side < 0].groupby("y").r.sum().round(1)
    p("R par annee et par brique (2008-2026):"); p(pv.fillna(0).to_string())
    # choix K sur departs 2008-2015 uniquement
    if K is None:
        best = None
        for k in (1.0, 1.5, 2.0, 2.5, 3.0):
            for mo, dds in itertools.product((4.0, 5.0), (0.06, 0.1)):
                s = summarize(challenge(tl, tb, W * k, start="2008-01-07", last_start="2015-12-31", guard=3.5, max_open=mo, dd_scale=dds))
                p(f"  DEV k{k} maxopen{mo} dds{dds}: reussite {s['pass_pct']:.0f}% echec {s['fail_pct']:.1f}% median {s['med_days']:.0f}j p90 {s['p90_days']:.0f}j")
                score = (s['fail_pct'] == 0, s['pass_pct'] >= 95, -s['med_days'])
                if best is None or score > best[0]: best = (score, k, mo, dds)
        _, K, MO, DDS = best
    else:
        MO, DDS = 5.0, 0.06
    p(f"REGLAGE RETENU: K {K} | risque ouvert max {MO}% | reduction DD {DDS * 100:.0f}%")
    for per, a, b in (("DEV 2008-2015", "2008-01-07", "2015-12-31"), ("TEST 2016-2025 (jamais vu)", "2016-01-04", "2025-11-01")):
        dfc = challenge(tl, tb, W * K, start=a, last_start=b, guard=3.5, max_open=MO, dd_scale=DDS); s = summarize(dfc)
        p(f"  CHALLENGE {per}: reussite {s['pass_pct']:.0f}% | echec {s['fail_pct']:.1f}% | median {s['med_days']:.0f}j | 75% {s['p75_days']:.0f}j | 90% {s['p90_days']:.0f}j | <=6 mois {s['in180']:.0f}%")
        dfc["y"] = dfc.start.dt.year
        p("    par annee de depart (median jours / echec%): " + str({y: (int(g.days.median()) if g.days.notna().any() else None, round((g.p1 == -1).mean() * 100)) for y, g in dfc.groupby("y")}))
    for kf in (K / 2,):
        for per, a in (("2008-2026", "2008-01-01"), ("2016-2026", "2016-01-01")):
            f, eq = funded(tl, tb, W * kf, start=a, guard=3.5, max_open=MO, dd_scale=DDS)
            p(f"  FINANCE K{kf} {per}: {f['per_month']:+.0f}$/mois | mois+ {f['pos_months']:.0f}% | pire mois {f['worst_month']:+.0f} | DD pic {f['dd_peak_pct']:.1f}% | statut {'OK' if f['status'] >= 0 else 'ECHEC'}")
            p(f"    annees: {f['years']}")
            windows(eq, per)
    return K

if __name__ == "__main__":
  KA = report("ADAPTATIF (achat + vente selon regime)", ADAPT, WA, None)
  report("v1.3 ACHAT SEUL (reglages 2020-2026, donc 2008-2019 = hors echantillon)", V13, WV, 2.0)
  open("/out/rapport_adaptatif.txt", "w").write("\n".join(L) + "\n")
