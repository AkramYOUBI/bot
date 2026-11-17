import itertools
import numpy as np, pandas as pd
import portfolio, strategies as S
from portfolio import build, challenge, components, funded, summarize
S.DELAY["h"] = 2; portfolio.REF_EQ[0] = 0
G = ["xauusd"]
SPEC = [("brk20", S.gold_breakout, {"rr": 3.0}, G), ("brk55", S.gold_breakout, {"en": 55, "ex": 20, "maxd": 30}, G),
        ("d7", S.double7, {}, G), ("mom", S.tsmom_w, {"look": 60}, G)]
C = components(SPEC); tl, tb = build(C)
W = np.array([1.0, 0.7, 0.8, 0.6])
res = []
for k, mo, gd, dds in itertools.product([1.5, 2.0, 2.5, 3.0], [3.0, 4.0, 5.0], [3.0, 3.5], [0.06, 0.1]):
    s = summarize(challenge(tl, tb, W * k, guard=gd, max_open=mo, dd_scale=dds))
    res.append(dict(k=k, maxopen=mo, guard=gd, dds=dds, **{x: round(s[x], 1) for x in ["pass_pct", "fail_pct", "med_days", "p75_days", "p90_days", "in180"]}))
df = pd.DataFrame(res)
print(df.sort_values(["fail_pct", "med_days"]).to_string(index=False))
