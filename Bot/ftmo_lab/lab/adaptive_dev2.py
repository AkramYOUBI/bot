import itertools
import numpy as np, pandas as pd
import strategies as S
from data import load
from adaptive_dev import st, DEV
S.DELAY["h"] = 2
I = load("xaulong")
for setup in ["pb", "rng"]:
    print(f"\n=== {setup} (DEV 2008-2015)")
    for th, sl, xm, sr in itertools.product([5, 10, 20], [2.0, 3.0], [3, 5], ([1.0] if setup == "pb" else [0.5, 1.0, 2.0])):
        kw = dict(th=th, sl=sl, exit_ma=xm, sr_atr=sr)
        print(f"  {str(kw):55s} {st(S.adaptive_mr(I, setup=setup, **kw), *DEV)}")
