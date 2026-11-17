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


# ---------------------------------------------------------------- 10) Cassure du range asiatique (intraday or)
def asian_breakout(I: Inst, r_end=8, last_entry=16, close_h=22, sl_mult=1.0, rr=1.5, dtrend=0, both=True, min_rng_atr=0.2, max_rng_atr=1.2):
    """Range des heures broker [1, r_end) ; cassure (cloture H1) entre r_end et last_entry ; sortie a close_h."""
    A = atr(I.dh, I.dl, I.dc, 14)
    DT = sma(I.dc, dtrend) if dtrend else None
    out = []
    for d in range(30, len(I.dc) - 1):
        f, l = int(I.d_first[d]), int(I.d_last[d])
        hrs = I.hour[f:l + 1]
        rng_idx = [f + j for j, h in enumerate(hrs) if 1 <= h < r_end]
        if len(rng_idx) < r_end - 2:
            continue
        hi = I.h[rng_idx].max(); lo = I.l[rng_idx].min()
        a = A[d - 1]
        if not a > 0 or not (min_rng_atr * a <= hi - lo <= max_rng_atr * a):
            continue
        up_ok = DT is None or I.dc[d - 1] > DT[d - 1]
        dn_ok = DT is None or I.dc[d - 1] < DT[d - 1]
        flag = np.zeros(len(I.c), bool)
        for k in range(rng_idx[-1] + 1, l + 1):
            if I.hour[k] >= close_h:
                flag[k - 1] = True
                break
        else:
            flag[l] = True
        for k in range(rng_idx[-1] + 1, l):
            h = I.hour[k]
            if h >= last_entry:
                break
            side = 1 if (I.c[k] > hi and up_ok) else (-1 if (both and I.c[k] < lo and dn_ok) else 0)
            if side == 0:
                continue
            dist = (hi - lo) * sl_mult
            res = run_trade(I, k + 1, side, dist, rr, flag, 30)
            if res is not None:
                out.append((res, side, I.dt[d]))
            break
    return out


# ---------------------------------------------------------------- 11) Momentum serie temporelle (hebdo)
def tsmom(I: Inst, look=60, hold=5, sl=3.0, both=False, ma=0):
    A = atr(I.dh, I.dl, I.dc, 20)
    M = sma(I.dc, ma) if ma else None
    f = np.zeros(len(I.c), bool)

    def sig(d):
        if d % hold != 0 or not A[d] > 0:
            return 0
        r = I.dc[d] / I.dc[d - look] - 1
        if r > 0 and (M is None or I.dc[d] > M[d]):
            return 1
        if both and r < 0 and (M is None or I.dc[d] < M[d]):
            return -1
        return 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, None, hold * 23)

    return _daily_loop(I, sig, mk, look + 5)


# ---------------------------------------------------------------- 12) Momentum hebdo calendaire (signal cloture vendredi)
def tsmom_w(I: Inst, look=60, sl=3.0, hold_days=4):
    A = atr(I.dh, I.dl, I.dc, 20)
    wd = I.dt.weekday.to_numpy()

    def sig(d):
        if wd[d] != 4 or not A[d] > 0:
            return 0
        return 1 if I.dc[d] > I.dc[d - look] else 0

    def mk(d, i0, side):
        return run_trade(I, i0, side, A[d] * sl, 0.0, None, hold_days * 23 + 12)

    return _daily_loop(I, sig, mk, look + 5)


# ================================================================ 13) LOGIQUE ADAPTATIVE OR (regime + S/R + RSI + EMA)
def _pivots(h, l, k=3):
    """Pivots fractals confirmes : le pivot en j n'est connu qu'a j+k (pas de regard futur)."""
    n = len(h)
    ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for j in range(k, n - k):
        if h[j] == h[j - k:j + k + 1].max():
            ph[j + k] = h[j]
        if l[j] == l[j - k:j + k + 1].min():
            pl[j + k] = l[j]
    return ph, pl


def regime_arrays(I: Inst, slope_n=10):
    c = I.dc
    E50, E200 = ema(c, 50), ema(c, 200)
    sl = np.zeros(len(c)); sl[slope_n:] = E50[slope_n:] - E50[:-slope_n]
    up = (c > E200) & (E50 > E200) & (sl > 0)
    dn = (c < E200) & (E50 < E200) & (sl < 0)
    reg = np.where(up, 1, np.where(dn, -1, 0))
    return reg, E50, E200


def adaptive(I: Inst, setup="pullback", look_sr=120, k_piv=3, rr=2.0, maxd=15, be_r=1.0,
             rsi_pb=40, rsi_rng=35, sr_tol=0.5, brk_en=20, brk_ex=10, brk_rr=3.0, sides=(1, -1)):
    c, h, l, o = I.dc, I.dh, I.dl, I.do
    A = atr(h, l, c, 20)
    R14 = rsi(c, 14)
    E20 = ema(c, 20)
    reg, E50, E200 = regime_arrays(I)
    ph, pl = _pivots(h, l, k_piv)
    H = hhv(h, brk_en); L = llv(l, brk_en); XL = llv(l, brk_ex); XH = hhv(h, brk_ex)
    nD = len(c)
    exL = np.zeros(nD, bool); exS = np.zeros(nD, bool)
    exL[1:] = c[1:] < XL[:-1]; exS[1:] = c[1:] > XH[:-1]
    fL, fS = _daily_flag(I, exL), _daily_flag(I, exS)
    out = []
    busy = -1
    for d in range(260, nD - 1):
        i0 = _entry_bar(I, d + 1)
        if i0 <= busy or not A[d] > 0:
            continue
        a = A[d]
        # supports / resistances confirmes sur look_sr jours
        lo_w = max(0, d - look_sr)
        ph_w = ph[lo_w:d + 1]; pl_w = pl[lo_w:d + 1]
        res_above = ph_w[ph_w > c[d]]; sup_below = pl_w[pl_w < c[d]]
        R = res_above.min() if res_above.size else np.nan
        Sp = sup_below.max() if sup_below.size else np.nan
        side, sld, tpr, flag, mx = 0, 0.0, rr, None, maxd
        if setup == "pullback" and reg[d] != 0:
            s = reg[d]
            if s in sides:
                rmin = R14[d - 3:d + 1].min() if s > 0 else R14[d - 3:d + 1].max()
                touched = (l[d - 3:d + 1].min() <= max(E50[d], E20[d]) + sr_tol * a) if s > 0 else \
                          (h[d - 3:d + 1].max() >= min(E50[d], E20[d]) - sr_tol * a)
                confirm = (c[d] > h[d - 1]) if s > 0 else (c[d] < l[d - 1])
                rsi_ok = (rmin < rsi_pb) if s > 0 else (rmin > 100 - rsi_pb)
                if touched and confirm and rsi_ok:
                    ext = l[d - 3:d + 1].min() if s > 0 else h[d - 3:d + 1].max()
                    sld = min(max(abs(c[d] - ext) + 0.5 * a, 1.0 * a), 3.0 * a)
                    side = s
        elif setup == "breakout" and reg[d] != 0:
            s = reg[d]
            if s in sides:
                if s > 0 and c[d] > H[d - 1] and c[d - 1] <= H[d - 2]:
                    side = 1
                elif s < 0 and c[d] < L[d - 1] and c[d - 1] >= L[d - 2]:
                    side = -1
                if side:
                    sld, tpr, flag, mx = 1.8 * a, brk_rr, (fL if side > 0 else fS), maxd
        elif setup == "range" and reg[d] == 0 and Sp == Sp and R == R and (R - Sp) > 3 * a:
            # achat sur support / vente sur resistance, RSI extreme + bougie de rejet
            if 1 in sides and l[d] <= Sp + sr_tol * a and R14[d] < rsi_rng + 10 and c[d] > o[d] and c[d] > Sp:
                side, sld = 1, (c[d] - Sp) + 1.0 * a
                tpr = max(0.8, ((Sp + R) / 2 - c[d]) / sld)
            elif -1 in sides and h[d] >= R - sr_tol * a and R14[d] > 100 - rsi_rng - 10 and c[d] < o[d] and c[d] < R:
                side, sld = -1, (R - c[d]) + 1.0 * a
                tpr = max(0.8, (c[d] - (Sp + R) / 2) / sld)
            mx = 10
        if side == 0:
            continue
        res = run_trade(I, i0, side, sld, tpr, flag, mx * 23, be_r=be_r)
        if res is None:
            continue
        out.append((res, side, I.dt[d + 1], int(reg[d])))
        busy = int(res[0][-1])
    return out


def adaptive_mr(I: Inst, setup="pb", th=10, sl=2.0, maxd=10, exit_ma=5, sr_atr=1.0, look_sr=120, k_piv=3, sides=(1, -1)):
    """pb : en tendance (regime), RSI2 extreme contre la tendance -> entree dans le sens de la tendance.
       rng : regime neutre, RSI2 extreme pres d'un support (achat) / d'une resistance (vente)."""
    c, h, l = I.dc, I.dh, I.dl
    A = atr(h, l, c, 20)
    R2 = rsi(c, 2)
    X = sma(c, exit_ma)
    reg, E50, E200 = regime_arrays(I)
    ph, pl = _pivots(h, l, k_piv)
    fL = _daily_flag(I, c > X); fS = _daily_flag(I, c < X)
    out = []; busy = -1
    for d in range(260, len(c) - 1):
        i0 = _entry_bar(I, d + 1)
        if i0 <= busy or not A[d] > 0:
            continue
        side = 0
        if setup == "pb":
            if reg[d] == 1 and 1 in sides and R2[d] < th:
                side = 1
            elif reg[d] == -1 and -1 in sides and R2[d] > 100 - th:
                side = -1
        else:
            if reg[d] != 0:
                continue
            lo_w = max(0, d - look_sr)
            ph_w = ph[lo_w:d + 1]; pl_w = pl[lo_w:d + 1]
            sup = pl_w[pl_w < c[d]]; res_ = ph_w[ph_w > c[d]]
            Sp = sup.max() if sup.size else np.nan; Rr = res_.min() if res_.size else np.nan
            if 1 in sides and R2[d] < th and Sp == Sp and c[d] - Sp <= sr_atr * A[d]:
                side = 1
            elif -1 in sides and R2[d] > 100 - th and Rr == Rr and Rr - c[d] <= sr_atr * A[d]:
                side = -1
        if side == 0:
            continue
        res = run_trade(I, i0, side, A[d] * sl, 0.0, fL if side > 0 else fS, maxd * 23)
        if res is None:
            continue
        out.append((res, side, I.dt[d + 1], int(reg[d])))
        busy = int(res[0][-1])
    return out


def regime_mom(I: Inst, look=60, sl=3.0, hold_days=4, sides=(1, -1)):
    """Momentum hebdo (vendredi) dans le sens du regime : achat si regime haussier et c > c[-look], vente si baissier."""
    A = atr(I.dh, I.dl, I.dc, 20)
    reg, _, _ = regime_arrays(I)
    wd = I.dt.weekday.to_numpy()
    def sig(d):
        if wd[d] != 4 or not A[d] > 0:
            return 0
        if reg[d] == 1 and 1 in sides and I.dc[d] > I.dc[d - look]:
            return 1
        if reg[d] == -1 and -1 in sides and I.dc[d] < I.dc[d - look]:
            return -1
        return 0
    return _daily_loop(I, sig, lambda d, i0, s: run_trade(I, i0, s, A[d] * sl, 0.0, None, hold_days * 23 + 12), 260)


def regime_d7(I: Inst, n=7, sl=3.0, maxd=10, sides=(1, -1)):
    """Double-7 dans le sens du regime : achat au plus bas 7j si haussier, vente au plus haut 7j si baissier."""
    A = atr(I.dh, I.dl, I.dc, 20)
    reg, _, _ = regime_arrays(I)
    LO = llv(I.dc, n); HI = hhv(I.dc, n)
    fL = _daily_flag(I, I.dc >= HI); fS = _daily_flag(I, I.dc <= LO)
    def sig(d):
        if not A[d] > 0:
            return 0
        if reg[d] == 1 and 1 in sides and I.dc[d] <= LO[d]:
            return 1
        if reg[d] == -1 and -1 in sides and I.dc[d] >= HI[d]:
            return -1
        return 0
    return _daily_loop(I, sig, lambda d, i0, s: run_trade(I, i0, s, A[d] * sl, 0.0, fL if s > 0 else fS, maxd * 23), 260)
