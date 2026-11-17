import numpy as np, pandas as pd
import data, portfolio, strategies as S
from portfolio import build, challenge, components, funded, summarize
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
G = ["xauusd"]
SPEC = [("brk20", S.gold_breakout, {"rr": 3.0}, G), ("brk55", S.gold_breakout, {"en": 55, "ex": 20, "maxd": 30}, G),
        ("d7", S.double7, {}, G), ("mom", S.tsmom_w, {"look": 60}, G)]
W = np.array([1.0, 0.7, 0.8, 0.6]); KC, KF = 2.0, 1.0
OPT = dict(guard=3.5, max_open=5.0, dd_scale=0.06)
L = []
def p(s): print(s, flush=True); L.append(s)
def bloc(tag):
    C = components(SPEC); tl, tb = build(C)
    df = challenge(tl, tb, W * KC, **OPT); s = summarize(df)
    p(f"[{tag}] CHALLENGE x{KC}: reussite {s['pass_pct']:.1f}% | echec {s['fail_pct']:.1f}% | median {s['med_days']:.0f}j | 75% {s['p75_days']:.0f}j | 90% {s['p90_days']:.0f}j | <=6 mois {s['in180']:.0f}%")
    df["y"] = df.start.dt.year
    p(df.groupby("y").agg(reussi=("p2", lambda x: (x == 1).mean() * 100), echec=("p1", lambda x: (x == -1).mean() * 100), jours_med=("days", "median")).round(0).to_string())
    for kf in (0.75, KF, 1.25):
        f, _ = funded(tl, tb, W * kf, **OPT)
        p(f"[{tag}] FINANCE x{kf}: {f['per_month']:+.0f}$/mois moyen | mois+ {f['pos_months']:.0f}% | pire mois {f['worst_month']:+.0f} | DD pic {f['dd_peak_pct']:.1f}% | pire jour {f['max_daily_loss']:.0f} | {f['years']}")
p("RAPPORT OR SEUL (XAUUSD) — 4 briques : cassure 20j TP3R (w1.0), cassure 55j (w0.7), Double-7 (w0.8), momentum 60j hebdo (w0.6)")
p(f"Reglages: K challenge {KC} | garde-fou 3.5% | risque ouvert max 5% | reduction DD 6%")
bloc("BASE")
for k in list(data.EXTRA): data.EXTRA[k] *= 2
data.SWAP_YEAR = 0.10; data.load.cache_clear()
bloc("COUTSx2")
open("/out/rapport_or_seul.txt", "w").write("\n".join(L) + "\n")
