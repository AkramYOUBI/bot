import numpy as np, pandas as pd
from research5 import *
tl, tb = build(COMPS)
# pire perte journaliere par composant (MTM), risque 1 % chacun -> en R
rows = []
for q, r in enumerate(tb.sorted_rows):
    g0, g1, sid, w, c, fin, sym, side, meta = r
    days = tl.day_codes[g0:g1 + 1]
    prev = 0.0; d0 = days[0]
    for j in range(len(w)):
        if days[j] != d0:
            prev = c[j - 1]; d0 = days[j]
        rows.append((tl.days[days[j]], meta, w[j] - prev))
df = pd.DataFrame(rows, columns=["d", "comp", "loss"])
worst = df.groupby(["d", "comp"])["loss"].min().reset_index()
worst["wloss"] = worst.apply(lambda x: x.loss * W[x.comp], axis=1)
day = worst.groupby("d")["wloss"].sum().sort_values()
print("pires jours (somme poids x R, pire intrabar):"); print(day.head(12).round(2).to_string())
for d in day.index[:5]:
    print(d.date(), worst[worst.d == d].sort_values("wloss").head(6)[["comp", "loss", "wloss"]].round(2).to_string(index=False))
print("\npires pertes R par trade:")
fins = pd.DataFrame([(r[8], tl.days[tl.day_codes[r[0]]], r[5], r[3].min()) for r in tb.sorted_rows], columns=["comp", "d", "fin", "mae"])
print(fins.sort_values("fin").head(10).round(2).to_string(index=False))
