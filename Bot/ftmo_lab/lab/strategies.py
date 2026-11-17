# -*- coding: utf-8 -*-
"""Strategies candidates. Chaque fonction renvoie la liste des trades (resultats run_trade) d'un instrument.
Signal sur cloture -> entree a l'ouverture de la barre suivante (pas de regard vers le futur)."""
from __future__ import annotations

import numpy as np

from data import Inst, atr, ema, hhv, llv, rsi, sma
from engine import run_trade


DELAY = {"h": 0}  # heures apres le debut du jour broker pour entrer/sortir (evite la reouverture)


def _entry_bar(I: Inst, d):
    i = int(I.d_first[d])
    last = int(I.d_last[d])
    while i < last and I.hour[i] < DELAY["h"]:
        i += 1
    return i


def _daily_loop(I: Inst, signal_fn, make_trade, start_d=210):
    """Boucle jours : signal a la cloture du jour d -> entree 1ere barre H1 du jour d+1.
    Une seule position par (strategie, instrument)."""
    out = []
    busy_until = -1
    nD = len(I.dc)
    for d in range(start_d, nD - 1):
        i0 = _entry_bar(I, d + 1)
        if i0 <= busy_until:
            continue
        side = signal_fn(d)
        if side == 0:
            continue
        res = make_trade(d, i0, side)
        if res is None:
            continue
        out.append((res, side, I.dt[d + 1]))
        busy_until = int(res[0][-1])
    return out


def _daily_flag(I: Inst, cond_daily: np.ndarray):
    """condition vraie a la cloture du jour k -> sortie a l'ouverture de la barre d'entree du jour k+1."""
    f = np.zeros(len(I.c), bool)
    nD = len(I.d_last)
    for k in np.nonzero(cond_daily[:nD])[0]:
        if k + 1 < nD:
            f[max(_entry_bar(I, k + 1) - 1, 0)] = True
    return f


# ---------------------------------------------------------------- 1) Or cassure D1 (GoldFTMO actuel)
def gold_breakout(I: Inst, en=20, ex=10, sl=1.8, rr=2.0, ema_n=50, maxd=15, cap=2.2, both=False):
    A = atr(I.dh, I.dl, I.dc, 20)
    Aavg = sma(A, 50)
    E = ema(I.dc, ema_n)
    H = hhv(I.dh, en); L = llv(I.dl, en)
    XL = llv(I.dl, ex); XH = hhv(I.dh, ex)
    exitL = np.zeros(len(I.dc), bool); exitS = np.zeros(len(I.dc), bool)
    exitL[1:] = I.dc[1:] < XL[:-1]
    exitS[1:] = I.dc[1:] > XH[:-1]
    fL, fS = _daily_flag(I, exitL), _daily_flag(I, exitS)

    def sig(d):
        if not (A[d] > 0) or (cap and Aavg[d] > 0 and A[d] > cap * Aavg[d]):
            return 0
        if I.dc[d] > H[d - 1] and I.dc[d - 1] <= H[d - 2] and (not ema_n or (I.dc[d] > E[d] and E[d] > E[d - 3])):
            return 1
        if both and I.dc[d] < L[d - 1] and I.dc[d - 1] >= L[d - 2] and (not ema_n or (I.dc[d] < E[d] and E[d] < E[d - 3])):
            return -1
        return 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, rr, fL if side > 0 else fS, maxd * 23)

    return _daily_loop(I, sig, mk, 60)


# ---------------------------------------------------------------- 2) Retour a la moyenne RSI(2) (indices / or)
def rsi2_mr(I: Inst, th=10, trend=200, exit_ma=5, sl=3.0, maxd=10, rsi_n=2, short=False):
    A = atr(I.dh, I.dl, I.dc, 20)
    R = rsi(I.dc, rsi_n)
    T = sma(I.dc, trend)
    X = sma(I.dc, exit_ma)
    fL = _daily_flag(I, I.dc > X)
    fS = _daily_flag(I, I.dc < X)

    def sig(d):
        if not (A[d] > 0 and T[d] > 0):
            return 0
        if I.dc[d] > T[d] and R[d] < th:
            return 1
        if short and I.dc[d] < T[d] and R[d] > 100 - th:
            return -1
        return 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, fL if side > 0 else fS, maxd * 23)

    return _daily_loop(I, sig, mk, trend + 5)


# ---------------------------------------------------------------- 3) Tendance Donchian D1 (turtle) toutes classes
def donchian(I: Inst, en=55, ex=20, sl=2.0, both=True, ema_n=0, maxd=60, trail=0.0, tp=0.0):
    A = atr(I.dh, I.dl, I.dc, 20)
    H = hhv(I.dh, en); L = llv(I.dl, en)
    XL = llv(I.dl, ex); XH = hhv(I.dh, ex)
    E = ema(I.dc, ema_n) if ema_n else None
    exitL = np.zeros(len(I.dc), bool); exitS = np.zeros(len(I.dc), bool)
    exitL[1:] = I.dc[1:] < XL[:-1]
    exitS[1:] = I.dc[1:] > XH[:-1]
    fL, fS = _daily_flag(I, exitL), _daily_flag(I, exitS)

    def sig(d):
        if not A[d] > 0:
            return 0
        if I.dc[d] > H[d - 1] and (E is None or I.dc[d] > E[d]):
            return 1
        if both and I.dc[d] < L[d - 1] and (E is None or I.dc[d] < E[d]):
            return -1
        return 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, tp, fL if side > 0 else fS, maxd * 23, trail=A[d] * trail)

    return _daily_loop(I, sig, mk, max(en, ema_n) + 5)


# ---------------------------------------------------------------- 4) Or H1 cassure long (rapide)
def h1_breakout(I: Inst, en=36, ex=18, sl=2.2, rr=2.0, ema_n=0, maxh=15 * 23, both=False, hours=None):
    A = atr(I.h, I.l, I.c, 20)
    H = hhv(I.h, en); L = llv(I.l, en)
    XL = llv(I.l, ex); XH = hhv(I.h, ex)
    E = ema(I.c, ema_n) if ema_n else None
    fL = np.zeros(len(I.c), bool); fS = np.zeros(len(I.c), bool)
    fL[1:] = I.c[1:] < XL[:-1]; fS[1:] = I.c[1:] > XH[:-1]
    out = []
    busy = -1
    hr = ((I.t // 3600) % 24)
    for k in range(max(en, ema_n, 25) + 2, len(I.c) - 1):
        if k + 1 <= busy or not A[k] > 0:
            continue
        if hours is not None and hr[k + 1] not in hours:
            continue
        side = 0
        if I.c[k] > H[k - 1] and I.c[k - 1] <= H[k - 2] and (E is None or I.c[k] > E[k]):
            side = 1
        elif both and I.c[k] < L[k - 1] and I.c[k - 1] >= L[k - 2] and (E is None or I.c[k] < E[k]):
            side = -1
        if side == 0:
            continue
        res = run_trade(I, k + 1, side, A[k] * sl, rr, fL if side > 0 else fS, maxh)
        if res is None:
            continue
        out.append((res, side, I.dt[I.bday[k + 1]]))
        busy = int(res[0][-1])
    return out


# ---------------------------------------------------------------- 5) Indices : achat apres baisse de N jours (tendance haussiere)
def down_days(I: Inst, n=3, trend=200, sl=3.0, maxd=7, exit_ma=0):
    A = atr(I.dh, I.dl, I.dc, 20)
    T = sma(I.dc, trend)
    up = np.zeros(len(I.dc), bool)
    up[1:] = I.dc[1:] > I.dc[:-1]
    if exit_ma:
        X = sma(I.dc, exit_ma)
        f = _daily_flag(I, I.dc > X)
    else:
        f = _daily_flag(I, up)

    def sig(d):
        if not (A[d] > 0 and T[d] > 0) or I.dc[d] < T[d]:
            return 0
        if all(I.dc[d - j] < I.dc[d - j - 1] for j in range(n)):
            return 1
        return 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, f, maxd * 23)

    return _daily_loop(I, sig, mk, trend + 5)


# ---------------------------------------------------------------- 6) IBS (internal bar strength) indices
def ibs_mr(I: Inst, lo=0.2, trend=200, sl=3.0, maxd=5, exit_ibs=0.0, exit_prevhigh=True):
    A = atr(I.dh, I.dl, I.dc, 20)
    T = sma(I.dc, trend) if trend else np.zeros(len(I.dc))
    rng = np.maximum(I.dh - I.dl, 1e-12)
    ibs = (I.dc - I.dl) / rng
    cond = np.zeros(len(I.dc), bool)
    if exit_prevhigh:
        cond[1:] |= I.dc[1:] > I.dh[:-1]
    if exit_ibs:
        cond |= ibs > exit_ibs
    if not exit_prevhigh and not exit_ibs:
        cond[:] = True
    f = _daily_flag(I, cond)

    def sig(d):
        if not A[d] > 0 or (trend and I.dc[d] < T[d]):
            return 0
        return 1 if ibs[d] < lo else 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, f, maxd * 23)

    return _daily_loop(I, sig, mk, max(trend, 25) + 5)


# ---------------------------------------------------------------- 7) Double 7 (Connors)
def double7(I: Inst, n=7, trend=200, sl=3.0, maxd=10):
    A = atr(I.dh, I.dl, I.dc, 20)
    T = sma(I.dc, trend)
    LO = llv(I.dc, n); HI = hhv(I.dc, n)
    f = _daily_flag(I, I.dc >= HI)

    def sig(d):
        if not (A[d] > 0 and T[d] > 0) or I.dc[d] < T[d]:
            return 0
        return 1 if I.dc[d] <= LO[d] else 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, f, maxd * 23)

    return _daily_loop(I, sig, mk, trend + 5)


# ---------------------------------------------------------------- 8) Fin de mois (turn of month)
def tom(I: Inst, before=4, after=3, sl=3.0, trend=0):
    A = atr(I.dh, I.dl, I.dc, 20)
    T = sma(I.dc, trend) if trend else None
    m = I.dt.month.to_numpy()
    nD = len(I.dc)
    # rang depuis la fin du mois et depuis le debut
    from_end = np.zeros(nD, int); from_start = np.zeros(nD, int)
    for d in range(nD):
        j = d
        while j + 1 < nD and m[j + 1] == m[d]:
            j += 1
        from_end[d] = j - d  # 0 = dernier jour du mois
    for d in range(nD):
        j = d
        while j - 1 >= 0 and m[j - 1] == m[d]:
            j -= 1
        from_start[d] = d - j + 1  # 1 = premier jour
    exitc = (from_start == after) & (from_start < 15)
    f = _daily_flag(I, exitc)

    def sig(d):
        if not A[d] > 0 or (T is not None and I.dc[d] < T[d]):
            return 0
        return 1 if from_end[d] == before else 0  # signal a la cloture -> entree le jour suivant

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, f, 12 * 23)

    return _daily_loop(I, sig, mk, 30)


# ---------------------------------------------------------------- 9) Retour a la moyenne intraday H1 (tendance D1 haussiere)
def h1_mr(I: Inst, rsi_n=2, th=5, exit_ma=5, sl=3.0, maxh=24, dtrend=200, hours=None, ibs=False, ibs_lo=0.15):
    A = atr(I.h, I.l, I.c, 20)
    R = rsi(I.c, rsi_n)
    X = sma(I.c, exit_ma)
    DT = sma(I.dc, dtrend) if dtrend else None
    f = I.c > X
    out = []
    busy = -1
    rng = np.maximum(I.h - I.l, 1e-12)
    ib = (I.c - I.l) / rng
    for k in range(60, len(I.c) - 1):
        if k + 1 <= busy or not A[k] > 0:
            continue
        if hours is not None and I.hour[k + 1] not in hours:
            continue
        dprev = I.bday[k] - 1
        if DT is not None and (dprev < dtrend or not (I.dc[dprev] > DT[dprev])):
            continue
        ok = (ib[k] < ibs_lo) if ibs else (R[k] < th)
        if not ok:
            continue
        res = run_trade(I, k + 1, 1, A[k] * sl, 0.0, f, maxh)
        if res is None:
            continue
        out.append((res, 1, I.dt[I.bday[k + 1]]))
        busy = int(res[0][-1])
    return out
