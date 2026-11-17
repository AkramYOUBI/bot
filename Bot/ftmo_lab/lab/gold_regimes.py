# Les regimes de l'or 2008-2026 + spread reel par epoque
import numpy as np, pandas as pd
from data import load
I = load("xaulong")
s = pd.Series(I.dc, index=I.dt)
print("Or fin d'annee:", {d.year: round(v) for d, v in s.resample("YE").last().items()})
sp = pd.Series((I.ao - I.o) / I.o * 1e4, index=pd.to_datetime(I.t, unit="s"))
print("spread median bps par annee:", sp.resample("YE").median().round(1).to_dict())
