# -*- coding: utf-8 -*-
"""
Formule risque/gain FTMO 100k pour GoldFTMO (cassure 20j, achat).
Telecharge XAUUSD journalier, simule, teste plusieurs risques.
Ecrit Bot/formule_ftmo.txt
"""
from __future__ import annotations

import json
import math
import os
import ssl
import time
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "formule_ftmo.txt")
INITIAL = 100000.0
DAILY = 0.05
MAXLOSS = 0.10
ENTRY_N, EXIT_N, ATR_N, SL_ATR = 20, 10, 20, 2.0
PARTIAL_R, PARTIAL_PCT = 1.0, 0.50
LOCK_R, MIN_RR, MAX_DAYS = 2.0, 2.0, 15
EMA = 50
PAUSE_AFTER, PAUSE_DAYS = 2, 8
SPREAD = 0.50  # $ or future approx


def http_json(url: str):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(last)


def download():
    p2 = int(time.time()) + 86400
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
        f"?period1=1262304000&period2={p2}&interval=1d"
    )
    res = http_json(url)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        d = datetime.fromtimestamp(t, timezone.utc).date()
        if d.weekday() >= 5:
            continue
        rows.append((d, float(o), float(h), float(l), float(c)))
    return rows


def atr_wilder(rows, n):
    trs = [0.0]
    for i in range(1, len(rows)):
        _, _, h, l, c = rows[i]
        pc = rows[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = [None] * len(rows)
    if len(trs) < n + 1:
        return out
    acc = sum(trs[1 : n + 1]) / n
    out[n] = acc
    for i in range(n + 1, len(rows)):
        out[i] = (out[i - 1] * (n - 1) + trs[i]) / n
    return out


def ema(closes, n):
    out = [None] * len(closes)
    if len(closes) < n:
        return out
    out[n - 1] = sum(closes[:n]) / n
    a = 2.0 / (n + 1.0)
    for i in range(n, len(closes)):
        out[i] = a * closes[i] + (1.0 - a) * out[i - 1]
    return out


def simulate(rows, risk_pct, use_ema=True, use_pause=True):
    closes = [r[4] for r in rows]
    atrs = atr_wilder(rows, ATR_N)
    emas = ema(closes, EMA)
    atr_avg = [None] * len(rows)
    for i in range(len(rows)):
        if i < ATR_N + 50:
            continue
        window = [atrs[j] for j in range(i - 49, i + 1) if atrs[j]]
        if len(window) == 50:
            atr_avg[i] = sum(window) / 50.0

    bal = INITIAL
    peak_bal = INITIAL
    max_dd = 0.0
    max_dd_abs = 0.0  # from initial
    day_start = bal
    trades = 0
    wins = 0
    losses = 0
    streak = 0
    pause_until = -1
    breached_daily = False
    breached_max = False
    equity_curve = []

    i = max(ENTRY_N + 5, EMA + 5)
    while i < len(rows) - 1:
        d, o, h, l, c = rows[i]
        atr = atrs[i]
        if atr is None or atr <= 0:
            i += 1
            continue

        # new day floor (daily bars = each bar is a day)
        day_start = bal

        if use_pause and i < pause_until:
            i += 1
            continue

        # signal: close breaks prior 20-day high (bars i-1.. relative)
        # use confirmed close of bar i as signal, enter next open i+1
        hh = max(rows[j][2] for j in range(i - ENTRY_N, i))
        hh_prev = max(rows[j][2] for j in range(i - 1 - ENTRY_N, i - 1))
        c_prev = rows[i - 1][4]
        if not (c > hh and c_prev <= hh_prev):
            i += 1
            continue

        if use_ema and (emas[i] is None or c < emas[i] or emas[i] <= emas[i - 3]):
            i += 1
            continue

        if atr_avg[i] and atr > atr_avg[i] * 2.2:
            i += 1
            continue

        # enter next day open
        if i + 1 >= len(rows):
            break
        entry = rows[i + 1][1] + SPREAD  # open + spread
        dist = atr * SL_ATR
        sl = entry - dist
        risk_money = INITIAL * risk_pct  # fixed on initial like EA
        # lot: $1 move = $100 per lot
        if dist <= 0:
            i += 1
            continue
        lots = risk_money / (dist * 100.0)
        if lots <= 0:
            i += 1
            continue

        if bal - risk_money <= day_start - DAILY * INITIAL:
            i += 1
            continue
        if bal - risk_money <= INITIAL * (1.0 - MAXLOSS):
            i += 1
            continue

        # TP = max(2R, next resistance approx = entry + 2R default)
        tp = entry + dist * MIN_RR
        # find next swing high above entry in past 80
        for j in range(i, max(ENTRY_N, i - 80), -1):
            if rows[j][2] > entry + dist * 0.5:
                # crude: use recent high above
                pass
        # walk forward
        partial_done = False
        peak = entry
        frozen = dist
        entry_i = i + 1
        exit_i = None
        exit_px = None
        pnl = 0.0
        vol = lots

        for k in range(entry_i, min(len(rows), entry_i + MAX_DAYS + 1)):
            dk, ok, hk, lk, ck = rows[k]
            # intraday path: worst low first for SL, then high for TP/partial
            # check SL hit
            if lk <= sl:
                exit_px = sl
                exit_i = k
                pnl = (exit_px - entry) * 100.0 * vol
                break
            peak = max(peak, hk)
            gain = hk - entry
            # partial at +1R on high
            if not partial_done and PARTIAL_R > 0 and gain >= dist * PARTIAL_R:
                close_vol = vol * PARTIAL_PCT
                pnl += (entry + dist * PARTIAL_R - entry) * 100.0 * close_vol
                vol -= close_vol
                sl = entry  # BE
                partial_done = True
            # lock trail
            if gain >= dist * LOCK_R:
                nsl = max(entry, ck - atr)
                sl = max(sl, nsl)
            else:
                nsl = peak - frozen
                if partial_done:
                    nsl = max(nsl, entry)
                sl = max(sl, nsl) if nsl > sl else sl
            # TP
            if hk >= tp:
                exit_px = tp
                exit_i = k
                pnl += (exit_px - entry) * 100.0 * vol
                vol = 0.0
                break
            # exit structure: close < 10-day low
            if k >= entry_i + 1:
                exit_low = min(rows[j][3] for j in range(k - EXIT_N, k))
                if ck < exit_low:
                    exit_px = ck - SPREAD
                    exit_i = k
                    pnl += (exit_px - entry) * 100.0 * vol
                    vol = 0.0
                    break
            # time
            if k - entry_i >= MAX_DAYS:
                exit_px = ck - SPREAD
                exit_i = k
                pnl += (exit_px - entry) * 100.0 * vol
                vol = 0.0
                break

        if exit_i is None:
            # force close last
            exit_i = min(len(rows) - 1, entry_i + MAX_DAYS)
            exit_px = rows[exit_i][4]
            pnl += (exit_px - entry) * 100.0 * vol

        # daily / max breach using worst equity during trade approx = pnl if loss
        worst = min(0.0, pnl)
        if bal + worst <= day_start - DAILY * INITIAL + 1e-6:
            breached_daily = True
        if bal + worst <= INITIAL * (1.0 - MAXLOSS) + 1e-6:
            breached_max = True

        bal += pnl
        trades += 1
        if pnl >= 0:
            wins += 1
            streak = 0
        else:
            losses += 1
            streak += 1
            if use_pause and streak >= PAUSE_AFTER:
                pause_until = exit_i + PAUSE_DAYS
                streak = 0

        peak_bal = max(peak_bal, bal)
        dd = peak_bal - bal
        max_dd = max(max_dd, dd)
        max_dd_abs = max(max_dd_abs, INITIAL - bal if bal < INITIAL else 0.0)
        equity_curve.append((rows[exit_i][0], bal))

        if bal <= INITIAL * (1.0 - MAXLOSS):
            breached_max = True
            break

        i = exit_i + 1

    months = max(1.0, (rows[-1][0] - rows[0][0]).days / 30.44)
    net = bal - INITIAL
    return {
        "risk": risk_pct,
        "net": net,
        "bal": bal,
        "trades": trades,
        "wr": (wins / trades * 100.0) if trades else 0.0,
        "max_dd_pct": max_dd / peak_bal * 100.0 if peak_bal else 0.0,
        "max_dd_from_init_pct": max_dd_abs / INITIAL * 100.0,
        "month": net / months,
        "ok_daily": not breached_daily,
        "ok_max": not breached_max and max_dd_abs / INITIAL < MAXLOSS - 1e-9,
        "ok_rel10": max_dd / peak_bal <= 0.10 + 1e-9 if peak_bal else True,
        "ftmo_safe": (not breached_daily)
        and (not breached_max)
        and (max_dd_abs / INITIAL <= MAXLOSS + 1e-9)
        and (max_dd / max(peak_bal, 1) <= 0.10 + 0.02),  # soft relative
    }


def main():
    rows = download()
    lines = []
    lines.append("FORMULE FTMO 100k — GoldFTMO (cassure 20j + EMA50 + pause 2 pertes)")
    lines.append(f"Donnees: {rows[0][0]} -> {rows[-1][0]}  n={len(rows)}")
    lines.append("Regles: jour -5%, total -10% depuis capital initial.")
    lines.append("")

    risks = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.045]
    results = []
    for r in risks:
        s = simulate(rows, r, use_ema=True, use_pause=True)
        results.append(s)
        flag = "OK FTMO" if s["ok_max"] and s["ok_daily"] and s["max_dd_from_init_pct"] <= 10.0 else "ECHEC FTMO"
        # also flag relative DD from peak > 10 as risky for psychology / some interpretations
        if s["max_dd_pct"] > 10.0:
            flag += " | trou depuis pic >10%"
        lines.append(
            f"risque {r*100:.1f}% | net {s['net']:+.0f}$ | ~/mois {s['month']:+.0f}$ | "
            f"trades {s['trades']} WR {s['wr']:.0f}% | DD init {s['max_dd_from_init_pct']:.1f}% | "
            f"DD pic {s['max_dd_pct']:.1f}% | {flag}"
        )

    # baseline without filters at 1%
    b = simulate(rows, 0.01, use_ema=False, use_pause=False)
    lines.append("")
    lines.append(
        f"Sans filtre @1%: net {b['net']:+.0f}$ | ~/mois {b['month']:+.0f}$ | DD pic {b['max_dd_pct']:.1f}%"
    )

    safe = [s for s in results if s["ok_max"] and s["ok_daily"] and s["max_dd_from_init_pct"] <= 8.0]
    # prefer also DD from peak under ~8%
    safe2 = [s for s in safe if s["max_dd_pct"] <= 8.0] or safe
    best = max(safe2, key=lambda z: z["month"]) if safe2 else None

    lines.append("")
    lines.append("=== FORMULE RETENUE ===")
    if best:
        lines.append(f"Risque par trade = {best['risk']*100:.1f}% du capital INITIAL")
        lines.append(f"Gain moyen simule ~= {best['month']:.0f}$ / mois")
        lines.append(f"Sur 100k: risque $ = {INITIAL * best['risk']:.0f}$ par trade")
        lines.append("Filtres: EMA50 D1 haussiere + pause 8j apres 2 pertes")
        lines.append("Plafonds robot: jour 5%, total 10%")
        if best["month"] >= 500:
            lines.append("Objectif 500$/mois: COUVERT dans cette simu")
        else:
            need = 500.0 / max(best["month"], 1.0)
            lines.append(
                f"Objectif 500$/mois: NON couvert a ce risque safe "
                f"(il faudrait ~{need:.1f}x le gain, donc plus de risque ou plus de capital)"
            )
            # capital needed for 500/mo at this monthly % rate
            monthly_pct = best["month"] / INITIAL
            if monthly_pct > 0:
                cap = 500.0 / monthly_pct
                lines.append(f"Pour ~500$/mois au meme % : capital ~= {cap:.0f}$ (ex: compte 200k)")
    else:
        lines.append("Aucun risque safe trouve — revoir filtres.")

    lines.append("")
    lines.append("Regle simple FTMO 100k:")
    lines.append("  risque% <= 5% / (pertes max consecutives visees)")
    lines.append("  avec pause a 2 pertes: risque% <= 2.0% (marge sous 5% jour et 10% total)")
    lines.append("  formule $ risque = capital * risque%")
    lines.append("  formule gain mensuel approx = (esperance R) * (trades/mois) * (capital * risque%)")

    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
