# Version VENTE (miroir) de chaque brique or, depuis 2020, en R, couts inclus
import numpy as np, pandas as pd
import strategies as S
from data import load, atr, sma, ema, hhv, llv
from engine import run_trade
from research1 import stats
S.DELAY["h"] = 2
I = load("xauusd")
A = atr(I.dh, I.dl, I.dc, 20)

def brk_short(en, ex, rr, maxd):
    E = ema(I.dc, 50); L = llv(I.dl, en); XH = hhv(I.dh, ex); Aavg = sma(A, 50)
    ex_ = np.zeros(len(I.dc), bool); ex_[1:] = I.dc[1:] > XH[:-1]; f = S._daily_flag(I, ex_)
    def sig(d):
        if not A[d] > 0 or (Aavg[d] > 0 and A[d] > 2.2 * Aavg[d]): return 0
        return -1 if (I.dc[d] < L[d-1] and I.dc[d-1] >= L[d-2] and I.dc[d] < E[d] and E[d] < E[d-3]) else 0
    return S._daily_loop(I, sig, lambda d, i0, s: run_trade(I, i0, s, A[d]*1.8, rr, f, maxd*23), 60)

def d7_short():
    T = sma(I.dc, 200); HI = hhv(I.dc, 7); LO = llv(I.dc, 7); f = S._daily_flag(I, I.dc <= LO)
    sig = lambda d: -1 if (I.dc[d] < T[d] and I.dc[d] >= HI[d]) else 0
    return S._daily_loop(I, sig, lambda d, i0, s: run_trade(I, i0, s, A[d]*3.0, 0.0, f, 10*23), 205)

def mom_short():
    wd = I.dt.weekday.to_numpy()
    sig = lambda d: -1 if (wd[d] == 4 and I.dc[d] < I.dc[d-60]) else 0
    return S._daily_loop(I, sig, lambda d, i0, s: run_trade(I, i0, s, A[d]*3.0, 0.0, None, 4*23+12), 65)

tests = {
    "ACHAT cassure 20j": S.gold_breakout(I, rr=3.0), "VENTE cassure 20j": brk_short(20, 10, 3.0, 15),
    "ACHAT cassure 55j": S.gold_breakout(I, en=55, ex=20, maxd=30), "VENTE cassure 55j": brk_short(55, 20, 2.0, 30),
    "ACHAT double-7": S.double7(I), "VENTE double-7": d7_short(),
    "ACHAT momentum 60j": S.tsmom_w(I, look=60), "VENTE momentum 60j": mom_short(),
}
for k, t in tests.items():
    st = stats(t)
    if st is None: print(f"{k:20s} aucun trade"); continue
    print(f"{k:20s} n={st['n']:4d} WR {st['wr']:3.0f}% moy {st['avg']:+.2f}R total {st['tot']:+6.1f}R pire DD {st['ddR']:4.1f}R | {st['yrs']}")
yr = pd.Series(I.dc, index=I.dt).resample("YE").last()
print("\nOr fin d'annee:", {d.year: round(v) for d, v in yr.items()})
