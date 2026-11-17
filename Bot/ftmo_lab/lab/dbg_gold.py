import numpy as np, pandas as pd
import portfolio, strategies as S
from portfolio import build, components, funded, run
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
G = ["xauusd"]
SPEC = [("brk20", S.gold_breakout, {"rr": 3.0}, G), ("brk55", S.gold_breakout, {"en": 55, "ex": 20, "maxd": 30}, G),
        ("d7", S.double7, {}, G), ("mom", S.tsmom_w, {"look": 60}, G)]
C = components(SPEC); tl, tb = build(C)
rows = tb.sorted_rows
print("trades par composant:", pd.Series([r[8] for r in rows]).value_counts().to_dict())
L = np.array([r[1] - r[0] for r in rows]); print("duree (barres globales) max:", L.max(), "median:", np.median(L))
big = sorted(rows, key=lambda r: r[1] - r[0])[-3:]
for r in big: print(r[8], tl.idx[r[0]], "->", tl.idx[r[1]], "final", round(r[5], 2))
f, eq = funded(tl, tb, np.array([1, 1, .6, .5]), guard=3.5, max_open=8.0, dd_scale=0.1)
print("trades pris:", f["trades"]); m = eq.resample("ME").last().diff(); print("mois a 0:", (m == 0).sum(), "/", len(m))
print(eq["2021-01":"2021-12"].resample("ME").last())
