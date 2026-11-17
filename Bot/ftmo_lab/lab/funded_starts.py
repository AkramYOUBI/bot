import numpy as np, pandas as pd
import portfolio, strategies as S
from portfolio import build, components, run
from adaptive_final import ADAPT, WA
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
tl, tb = build(components(ADAPT))
for k in (0.75, 1.0, 1.25, 1.5):
    res = []
    for d in pd.date_range("2008-01-01", "2025-11-01", freq="MS"):
        g0 = tl.gi_of_date(d); g1 = min(len(tl.t), tl.gi_of_date(d + pd.Timedelta(days=365)))
        st, gst, eq, mn, ntr, td, mdl, _ = run(tl, tb, WA * k, g0, g1, 0.0, 3.5, 4.0, 0, 0.06)
        res.append((st, eq - 1e5, mn))
    df = pd.DataFrame(res, columns=["st", "pnl", "mn"])
    print(f"FINANCE K{k} (depart chaque mois, 12 mois): casse -10% {(df.st == -1).mean() * 100:.1f}% | annee positive {(df.pnl > 0).mean() * 100:.0f}% | "
          f"gain median {df.pnl.median() / 12:+.0f}$/mois | pire annee {df.pnl.min():+.0f}$ | equity la plus basse {df.mn.min():.0f}$")
