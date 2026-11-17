# Saisonnalite horaire : rendement moyen par heure UTC, par annee (en % ) -> stabilite
import numpy as np, pandas as pd, sys
from data import load
for s in sys.argv[1:]:
    I = load(s)
    t = pd.to_datetime(I.t, unit="s", utc=True)
    r = (I.c - I.o) / I.o * 1e4  # bps
    df = pd.DataFrame({"y": t.year, "h": t.hour, "r": r})
    df = df[df.y >= 2020]
    piv = df.pivot_table(index="h", columns="y", values="r", aggfunc="mean").round(1)
    piv["all"] = df.groupby("h")["r"].mean().round(2)
    piv["t"] = (df.groupby("h")["r"].mean() / df.groupby("h")["r"].std() * np.sqrt(df.groupby("h").size())).round(1)
    print("\n==", s, "(bps/barre, heure UTC)  cout aller-retour bps ~", round(I.cost / I.c[-1] * 1e4, 1))
    print(piv.to_string())
