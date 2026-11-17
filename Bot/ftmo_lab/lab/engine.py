# -*- coding: utf-8 -*-
"""Moteur : (1) simulation d'un trade en R sur H1 (pessimiste), (2) compte FTMO multi-strategies (numba)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from data import SWAP_YEAR, Inst


# ------------------------------------------------------------------ trade unique
def run_trade(I: Inst, i0: int, side: int, sl_dist: float, tp_r: float = 0.0,
              exit_flag: np.ndarray | None = None, max_bars: int = 10**9,
              trail: float = 0.0, be_r: float = 0.0):
    """Entree a l'ouverture de la barre i0. Conflit SL/TP dans la meme barre -> SL.
    exit_flag[k] vrai -> sortie a l'ouverture de k+1. Retourne (bars, worstR, closeR, finalR)."""
    n = len(I.c)
    if i0 >= n - 1 or sl_dist <= 0:
        return None
    # achat au ask / vente au bid ; sortie achat au bid / sortie vente au ask ; + cout (commission)
    entry = (I.ao[i0] + I.cost) if side > 0 else (I.o[i0] - I.cost)
    sl = entry - side * sl_dist
    tp = entry + side * tp_r * sl_dist if tp_r > 0 else np.nan
    peak = entry
    bars, wr, cr = [], [], []
    swap_per_day = entry * I.swap / 365.0 / sl_dist
    d0 = I.bday[i0]
    final = None
    k = i0
    while k < n:
        if side > 0:   # sortie au bid
            o, h, l, c = I.o[k], I.h[k], I.l[k], I.c[k]
        else:          # sortie au ask
            o, h, l, c = I.ao[k], I.ah[k], I.al[k], I.ac[k]
        sw = (I.bday[k] - d0) * swap_per_day
        if side > 0:
            if k > i0 and o <= sl:
                final = (o - entry) / sl_dist
            elif l <= sl:
                final = (sl - entry) / sl_dist
            elif tp == tp and h >= tp:
                final = (max(o, tp) - entry) / sl_dist if k > i0 else (tp - entry) / sl_dist
            worst, close = (l - entry) / sl_dist, (c - entry) / sl_dist
        else:
            if k > i0 and o >= sl:
                final = (entry - o) / sl_dist
            elif h >= sl:
                final = (entry - sl) / sl_dist
            elif tp == tp and l <= tp:
                final = (entry - min(o, tp)) / sl_dist if k > i0 else (entry - tp) / sl_dist
            worst, close = (entry - h) / sl_dist, (entry - c) / sl_dist
        if final is not None:
            final -= sw
            bars.append(k); wr.append(min(final, worst - sw)); cr.append(final)
            break
        bars.append(k); wr.append(worst - sw); cr.append(close - sw)
        # gestion apres la barre
        if side > 0:
            peak = max(peak, h)
            if trail > 0:
                sl = max(sl, peak - trail)
            if be_r > 0 and (peak - entry) >= be_r * sl_dist:
                sl = max(sl, entry + 0.1 * sl_dist)
        else:
            peak = min(peak, l)
            if trail > 0:
                sl = min(sl, peak + trail)
            if be_r > 0 and (entry - peak) >= be_r * sl_dist:
                sl = min(sl, entry - 0.1 * sl_dist)
        if (exit_flag is not None and exit_flag[k]) or (k - i0 + 1 >= max_bars):
            if k + 1 < n:
                sw2 = (I.bday[k + 1] - d0) * swap_per_day
                px = I.o[k + 1] if side > 0 else I.ao[k + 1]
                final = side * (px - entry) / sl_dist - sw2
                bars.append(k + 1); wr.append(final); cr.append(final)
            else:
                final = cr[-1]
            break
        k += 1
    if final is None:
        return None
    return np.array(bars), np.array(wr), np.array(cr), float(final)


# ------------------------------------------------------------------ timeline globale
class Timeline:
    def __init__(self, insts):
        allt = np.unique(np.concatenate([I.t for I in insts]))
        self.t = allt
        idx = pd.to_datetime(allt, unit="s", utc=True).tz_convert("Europe/Prague")
        # jour FTMO = minuit Prague
        days = idx.tz_localize(None).normalize()
        self.day_codes, self.days = pd.factorize(days, sort=True)
        self.day_codes = self.day_codes.astype(np.int64)
        self.idx = idx

    def g(self, I: Inst, k):
        return np.searchsorted(self.t, I.t[k])

    def gi_of_date(self, d):
        ts = int(pd.Timestamp(d, tz="Europe/Prague").timestamp())
        return int(np.searchsorted(self.t, ts))


class TradeBook:
    """Liste de trades multi-strategies projetes sur la timeline globale."""

    def __init__(self, tl: Timeline):
        self.tl = tl
        self.rows = []  # (gstart, gend, sid, worst[], close[], final, sym, side, t_entry)

    def add(self, sid: int, I: Inst, res, side, meta=""):
        if res is None:
            return
        bars, wr, cr, final = res
        gb = np.searchsorted(self.tl.t, I.t[bars])
        g0, g1 = int(gb[0]), int(gb[-1])
        L = g1 - g0 + 1
        pos = np.searchsorted(gb, np.arange(g0, g1 + 1), side="right") - 1
        w = wr[pos].copy(); c = cr[pos].copy()
        # heures sans barre de l'instrument : on garde la derniere valeur close (pas de nouveau pire)
        exact = gb[pos] == np.arange(g0, g1 + 1)
        w[~exact] = c[~exact]
        w[-1] = min(w[-1], final); c[-1] = final
        self.rows.append((g0, g1, sid, w, c, final, I.name, side, meta))

    def pack(self):
        rows = sorted(self.rows, key=lambda r: r[0])
        n = len(rows)
        gs = np.array([r[0] for r in rows], np.int64)
        ge = np.array([r[1] for r in rows], np.int64)
        sid = np.array([r[2] for r in rows], np.int64)
        fin = np.array([r[5] for r in rows], float)
        off = np.zeros(n + 1, np.int64)
        off[1:] = np.cumsum([len(r[3]) for r in rows])
        W = np.concatenate([r[3] for r in rows]) if n else np.zeros(0)
        C = np.concatenate([r[4] for r in rows]) if n else np.zeros(0)
        self.packed = (gs, ge, sid, fin, off, W, C)
        self.sorted_rows = rows
        return self.packed


# ------------------------------------------------------------------ compte FTMO
@njit(cache=True)
def account(gs, ge, sid, fin, off, W, C, day_codes, risk, g_start, g_end,
            target, init, daily_guard, max_open_risk, min_days, dd_scale, rec_daily, ref_eq=1, up_boost=0.0):
    """status: 1 objectif atteint, -1 regle FTMO cassee, 0 fin des donnees.
    risk[s] = fraction du capital initial risquee par trade de la strategie s.
    daily_guard: le robot coupe tout si equity <= ref_jour - daily_guard*init (marge vs 5 %).
    dd_scale: si >0, risque *= max(0.3, 1 - dd/dd_scale) avec dd = perte vs initial (fraction)."""
    n = gs.shape[0]
    bal = init
    eq_close = init
    open_idx = np.empty(256, np.int64)
    open_risk = np.empty(256)
    n_open = 0
    p = 0
    while p < n and gs[p] < g_start:
        p += 1
    cur_day = -1
    day_ref = init
    day_halt = False
    traded_days = 0
    last_trade_day = -1
    min_eq = init
    ntr = 0
    ndays = day_codes[g_end - 1] - day_codes[g_start] + 1
    daily = np.full(ndays if rec_daily else 1, np.nan)
    status = 0
    g_stop = g_end
    max_daily_loss = 0.0
    for g in range(g_start, g_end):
        d = day_codes[g]
        if d != cur_day:
            if rec_daily and cur_day >= 0:
                daily[cur_day - day_codes[g_start]] = eq_close
            cur_day = d
            day_ref = max(bal, eq_close) if ref_eq else bal
            day_halt = False
        # ---- ouvertures
        while p < n and gs[p] == g:
            s = sid[p]
            r = risk[s]
            if r > 0 and not day_halt and n_open < 256:
                sc = 1.0
                if dd_scale > 0:
                    dd = (init - eq_close) / init
                    if dd > 0:
                        sc = max(0.3, 1.0 - dd / dd_scale)
                if up_boost > 0 and eq_close > init:
                    sc = min(1.0 + up_boost, 1.0 + (eq_close - init) / init * up_boost * 10.0)
                rm = init * r * sc
                tot = rm
                for j in range(n_open):
                    tot += open_risk[j]
                # pas d'entree si le pire cas (tous les stops) casse un plafond du robot
                if tot <= max_open_risk * init and eq_close - tot > init * 0.9 + 0.003 * init \
                        and eq_close - tot > day_ref - daily_guard * init:
                    open_idx[n_open] = p
                    open_risk[n_open] = rm
                    n_open += 1
                    ntr += 1
                    if d != last_trade_day:
                        traded_days += 1
                        last_trade_day = d
            p += 1
        # ---- valorisation
        worst = 0.0
        close = 0.0
        j = 0
        while j < n_open:
            q = open_idx[j]
            k = off[q] + (g - gs[q])
            worst += open_risk[j] * W[k]
            close += open_risk[j] * C[k]
            j += 1
        eq_w = bal + worst
        if eq_w < min_eq:
            min_eq = eq_w
        if day_ref - eq_w > max_daily_loss:
            max_daily_loss = day_ref - eq_w
        if eq_w <= day_ref - 0.05 * init or eq_w <= 0.9 * init:
            status = -1
            g_stop = g
            break
        # garde-fou robot : coupe la journee
        if n_open > 0 and eq_w <= day_ref - daily_guard * init:
            bal = day_ref - daily_guard * init - 0.002 * init
            n_open = 0
            day_halt = True
            eq_close = bal
            continue
        # ---- fermetures
        j = 0
        while j < n_open:
            q = open_idx[j]
            if ge[q] == g:
                bal += open_risk[j] * fin[q]
                open_idx[j] = open_idx[n_open - 1]
                open_risk[j] = open_risk[n_open - 1]
                n_open -= 1
            else:
                j += 1
        close = 0.0
        for j in range(n_open):
            q = open_idx[j]
            close += open_risk[j] * C[off[q] + (g - gs[q])]
        eq_close = bal + close
        if target > 0 and eq_close >= init * (1.0 + target) and traded_days >= min_days:
            bal = eq_close
            n_open = 0
            status = 1
            g_stop = g
            break
    if rec_daily and cur_day >= 0 and cur_day - day_codes[g_start] < ndays:
        daily[cur_day - day_codes[g_start]] = eq_close
    return status, g_stop, eq_close, min_eq, ntr, traded_days, max_daily_loss, daily
