import numpy as np, pandas as pd
import portfolio, strategies as S
from portfolio import build, funded
from research5 import COMPS, BASE
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
sub = [(c, b) for c, b in zip(COMPS, BASE) if c[3] == "xauusd"]
tl, tb = build([c for c, _ in sub])
f, eq = funded(tl, tb, np.array([b for _, b in sub]) * 0.75, guard=3.5, max_open=8.0, dd_scale=0.1)
n = sum(1 for r in tb.sorted_rows if tl.days[tl.day_codes[r[0]]] >= pd.Timestamp("2020-01-01"))
print(f"OR SEUL (2 briques) K0.75: net {f['net']:+.0f}$ | trades {f['trades']} | DD pic {f['dd_peak_pct']:.1f}% | annees {f['years']}")
