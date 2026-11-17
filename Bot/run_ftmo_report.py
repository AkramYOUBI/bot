# -*- coding: utf-8 -*-
"""
Rapport FTMO 100k depuis 2020 — GoldFTMO logique v6.2
Risque 1.0% et 1.5%. Compte floating DD. Dates de pass phase1/phase2.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from datetime import datetime, timezone, date

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rapport_ftmo_2020.txt")
INITIAL = 100000.0
ENTRY_N, EXIT_N, ATR_N, SL_ATR = 20, 10, 20, 2.0
PARTIAL_R, PARTIAL_PCT = 1.0, 0.50
LOCK_R, MIN_RR, MAX_DAYS = 2.0, 2.0, 15
EMA, PAUSE_AFTER, PAUSE_DAYS = 50, 2, 8
SPREAD = 0.40
DAILY, MAXLOSS = 0.05, 0.10
START = date(2020, 1, 1)


def http_json(url: str):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last = None
    for i in range(5):
        try:
            with urllib.request.urlopen(req, timeout=45, context=ctx) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
            time.sleep(1.3 * (i + 1))
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
    return [r for r in rows if r[0] >= date(2018, 1, 1)]


def atr_wilder(rows, n):
    trs = [0.0]
    for i in range(1, len(rows)):
        _, _, h, l, c = rows[i]
        pc = rows[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = [None] * len(rows)
    acc = sum(trs[1 : n + 1]) / n
    out[n] = acc
    for i in range(n + 1, len(rows)):
        out[i] = (out[i - 1] * (n - 1) + trs[i]) / n
    return out


def ema(closes, n):
    out = [None] * len(closes)
    out[n - 1] = sum(closes[:n]) / n
    a = 2.0 / (n + 1.0)
    for i in range(n, len(closes)):
        out[i] = a * closes[i] + (1.0 - a) * out[i - 1]
    return out


def run(rows, risk_pct: float):
    # start index at 2020
    start_i = next(i for i, r in enumerate(rows) if r[0] >= START)
    closes = [r[4] for r in rows]
    atrs = atr_wilder(rows, ATR_N)
    emas = ema(closes, EMA)
    atr_avg = [None] * len(rows)
    for i in range(len(rows)):
        if i < ATR_N + 50:
            continue
        w = [atrs[j] for j in range(i - 49, i + 1) if atrs[j]]
        if len(w) == 50:
            atr_avg[i] = sum(w) / 50.0

    bal = INITIAL
    peak_eq = INITIAL
    max_dd_eq = 0.0          # peak-to-trough equity (floating included)
    max_dd_from_init = 0.0   # INITIAL - min_equity
    min_eq = INITIAL
    day_breach = False
    max_breach = False
    trades = []
    streak = 0
    pause_until = -1

    phase1_date = None
    phase2_date = None
    # Phase2 = new account after phase1: track from phase1_end balance reset conceptually
    # FTMO: after pass phase1, NEW account for phase2. We simulate: when +10% hit, mark date,
    # reset bal to INITIAL, then when +5% mark phase2.
    mode = 1  # 1 or 2
    phase_start_bal = INITIAL
    phase_target = 0.10

    i = max(start_i, ENTRY_N + EMA + 5)
    end = len(rows) - 1

    while i < end:
        d, o, h, l, c = rows[i]
        atr = atrs[i]
        if atr is None or atr <= 0:
            i += 1
            continue
        if i < pause_until:
            i += 1
            continue

        hh = max(rows[j][2] for j in range(i - ENTRY_N, i))
        hh_prev = max(rows[j][2] for j in range(i - 1 - ENTRY_N, i - 1))
        c_prev = rows[i - 1][4]
        if not (c > hh and c_prev <= hh_prev):
            i += 1
            continue
        if emas[i] is None or c < emas[i] or emas[i] <= emas[i - 3]:
            i += 1
            continue
        if atr_avg[i] and atr > atr_avg[i] * 2.2:
            i += 1
            continue

        if i + 1 >= len(rows):
            break
        entry = rows[i + 1][1] + SPREAD
        dist = atr * SL_ATR
        if dist <= 0:
            i += 1
            continue
        risk_money = INITIAL * risk_pct
        lots = risk_money / (dist * 100.0)
        day_start = bal
        if bal - risk_money <= day_start - DAILY * INITIAL:
            i += 1
            continue
        if bal - risk_money <= INITIAL * (1.0 - MAXLOSS):
            i += 1
            continue

        sl = entry - dist
        tp = entry + dist * MIN_RR
        partial = False
        peak = entry
        vol = lots
        pnl = 0.0
        entry_i = i + 1
        worst_eq = bal  # floating during trade
        exit_i = entry_i
        exit_px = entry

        for k in range(entry_i, min(len(rows), entry_i + MAX_DAYS + 1)):
            hk, lk, ck = rows[k][2], rows[k][3], rows[k][4]
            # floating equity at worst of day (low)
            float_pnl = (lk - entry) * 100.0 * vol
            if partial:
                # already took partial at +1R locked
                float_pnl = (lk - entry) * 100.0 * vol  # remaining
            eq = bal + float_pnl
            # also check high float for peak
            float_hi = (hk - entry) * 100.0 * vol
            eq_hi = bal + float_hi
            peak_eq = max(peak_eq, eq_hi, bal)
            worst_eq = min(worst_eq, eq)
            min_eq = min(min_eq, eq)
            max_dd_eq = max(max_dd_eq, peak_eq - eq)
            max_dd_from_init = max(max_dd_from_init, INITIAL - eq)

            if eq <= day_start - DAILY * INITIAL:
                day_breach = True
            if eq <= INITIAL * (1.0 - MAXLOSS):
                max_breach = True

            if lk <= sl:
                exit_px = sl
                exit_i = k
                pnl += (exit_px - entry) * 100.0 * vol
                vol = 0.0
                break

            peak = max(peak, hk)
            gain = hk - entry
            if not partial and gain >= dist * PARTIAL_R:
                cv = vol * PARTIAL_PCT
                pnl += dist * PARTIAL_R * 100.0 * cv
                vol -= cv
                sl = entry
                partial = True
            if gain >= dist * LOCK_R:
                nsl = max(entry, ck - atr)
                sl = max(sl, nsl)
            else:
                nsl = peak - dist
                if partial:
                    nsl = max(nsl, entry)
                if nsl > sl:
                    sl = nsl

            if hk >= tp:
                exit_px = tp
                exit_i = k
                pnl += (exit_px - entry) * 100.0 * vol
                vol = 0.0
                break

            if k >= entry_i + 1:
                elow = min(rows[j][3] for j in range(k - EXIT_N, k))
                if ck < elow:
                    exit_px = ck - SPREAD
                    exit_i = k
                    pnl += (exit_px - entry) * 100.0 * vol
                    vol = 0.0
                    break

            if k - entry_i >= MAX_DAYS:
                exit_px = ck - SPREAD
                exit_i = k
                pnl += (exit_px - entry) * 100.0 * vol
                vol = 0.0
                break
            exit_i = k

        if vol > 0:
            exit_px = rows[exit_i][4]
            pnl += (exit_px - entry) * 100.0 * vol

        bal += pnl
        peak_eq = max(peak_eq, bal)
        min_eq = min(min_eq, bal)
        max_dd_eq = max(max_dd_eq, peak_eq - bal)
        max_dd_from_init = max(max_dd_from_init, max(0.0, INITIAL - bal))

        trades.append((rows[entry_i][0], rows[exit_i][0], pnl, bal))
        if pnl >= 0:
            streak = 0
        else:
            streak += 1
            if streak >= PAUSE_AFTER:
                pause_until = exit_i + PAUSE_DAYS
                streak = 0

        # FTMO phases
        if mode == 1 and bal >= phase_start_bal * (1.0 + phase_target):
            phase1_date = rows[exit_i][0]
            mode = 2
            # new verification account
            bal = INITIAL
            phase_start_bal = INITIAL
            phase_target = 0.05
            peak_eq = INITIAL
            # keep min_eq / max dd stats from whole journey too
        elif mode == 2 and bal >= phase_start_bal * (1.0 + phase_target):
            phase2_date = rows[exit_i][0]
            # continue funded on same risk for monthly estimate: keep running
            mode = 3  # funded
            # restore cumulative for monthly: better track funded separately
            # For monthly we use a continuous account without phase reset — see funded_bal below

        if bal <= INITIAL * (1.0 - MAXLOSS) and mode != 3:
            max_breach = True
            break

        i = exit_i + 1

    # Separate continuous funded-style run for monthly (no phase reset)
    cont = run_continuous(rows, risk_pct, start_i, atrs, emas, atr_avg)

    months = max(1.0, (rows[-1][0] - START).days / 30.44)
    return {
        "risk": risk_pct,
        "trades": len(trades),
        "phase1": phase1_date,
        "phase2": phase2_date,
        "day_breach": day_breach,
        "max_breach": max_breach,
        "max_dd_eq_pct": 100.0 * max_dd_eq / max(peak_eq, 1),
        "max_dd_from_init_pct": 100.0 * max_dd_from_init / INITIAL,
        "min_eq": min_eq,
        "cont": cont,
        "months": months,
    }


def run_continuous(rows, risk_pct, start_i, atrs, emas, atr_avg):
    """Compte finance continu depuis 2020 pour $/mois et DD floating."""
    bal = INITIAL
    peak_eq = INITIAL
    max_dd_eq = 0.0
    max_dd_from_init = 0.0
    min_eq = INITIAL
    day_breach = False
    max_breach = False
    streak = 0
    pause_until = -1
    pnls = []
    monthly = {}
    i = max(start_i, ENTRY_N + EMA + 5)
    end = len(rows) - 1
    first_10 = None
    first_15 = None

    while i < end:
        d, o, h, l, c = rows[i]
        atr = atrs[i]
        if atr is None or atr <= 0:
            i += 1
            continue
        if i < pause_until:
            i += 1
            continue
        hh = max(rows[j][2] for j in range(i - ENTRY_N, i))
        hh_prev = max(rows[j][2] for j in range(i - 1 - ENTRY_N, i - 1))
        c_prev = rows[i - 1][4]
        if not (c > hh and c_prev <= hh_prev):
            i += 1
            continue
        if emas[i] is None or c < emas[i] or emas[i] <= emas[i - 3]:
            i += 1
            continue
        if atr_avg[i] and atr > atr_avg[i] * 2.2:
            i += 1
            continue
        if i + 1 >= len(rows):
            break
        entry = rows[i + 1][1] + SPREAD
        dist = atr * SL_ATR
        if dist <= 0:
            i += 1
            continue
        risk_money = INITIAL * risk_pct
        lots = risk_money / (dist * 100.0)
        day_start = bal
        if bal - risk_money <= day_start - DAILY * INITIAL:
            i += 1
            continue
        if bal - risk_money <= INITIAL * (1.0 - MAXLOSS):
            i += 1
            continue

        sl = entry - dist
        tp = entry + dist * MIN_RR
        partial = False
        peak = entry
        vol = lots
        pnl = 0.0
        entry_i = i + 1
        exit_i = entry_i

        for k in range(entry_i, min(len(rows), entry_i + MAX_DAYS + 1)):
            hk, lk, ck = rows[k][2], rows[k][3], rows[k][4]
            float_pnl = (lk - entry) * 100.0 * vol
            eq = bal + float_pnl
            float_hi = (hk - entry) * 100.0 * vol
            peak_eq = max(peak_eq, bal + float_hi, bal)
            min_eq = min(min_eq, eq)
            max_dd_eq = max(max_dd_eq, peak_eq - eq)
            max_dd_from_init = max(max_dd_from_init, INITIAL - eq)
            if eq <= day_start - DAILY * INITIAL:
                day_breach = True
            if eq <= INITIAL * (1.0 - MAXLOSS):
                max_breach = True

            if lk <= sl:
                pnl += (sl - entry) * 100.0 * vol
                vol = 0.0
                exit_i = k
                break
            peak = max(peak, hk)
            gain = hk - entry
            if not partial and gain >= dist * PARTIAL_R:
                cv = vol * PARTIAL_PCT
                pnl += dist * PARTIAL_R * 100.0 * cv
                vol -= cv
                sl = entry
                partial = True
            if gain >= dist * LOCK_R:
                sl = max(sl, max(entry, ck - atr))
            else:
                nsl = peak - dist
                if partial:
                    nsl = max(nsl, entry)
                sl = max(sl, nsl)
            if hk >= tp:
                pnl += (tp - entry) * 100.0 * vol
                vol = 0.0
                exit_i = k
                break
            if k >= entry_i + 1:
                elow = min(rows[j][3] for j in range(k - EXIT_N, k))
                if ck < elow:
                    pnl += (ck - SPREAD - entry) * 100.0 * vol
                    vol = 0.0
                    exit_i = k
                    break
            if k - entry_i >= MAX_DAYS:
                pnl += (ck - SPREAD - entry) * 100.0 * vol
                vol = 0.0
                exit_i = k
                break
            exit_i = k

        if vol > 0:
            pnl += (rows[exit_i][4] - entry) * 100.0 * vol

        bal += pnl
        peak_eq = max(peak_eq, bal)
        min_eq = min(min_eq, bal)
        max_dd_eq = max(max_dd_eq, peak_eq - bal)
        max_dd_from_init = max(max_dd_from_init, max(0.0, INITIAL - bal))
        pnls.append(pnl)
        key = (rows[exit_i][0].year, rows[exit_i][0].month)
        monthly[key] = monthly.get(key, 0.0) + pnl

        if first_10 is None and bal >= INITIAL * 1.10:
            first_10 = rows[exit_i][0]
        if first_15 is None and bal >= INITIAL * 1.15:
            first_15 = rows[exit_i][0]

        if pnl >= 0:
            streak = 0
        else:
            streak += 1
            if streak >= PAUSE_AFTER:
                pause_until = exit_i + PAUSE_DAYS
                streak = 0

        if bal <= INITIAL * (1.0 - MAXLOSS):
            max_breach = True
            break
        i = exit_i + 1

    months = max(1.0, (rows[-1][0] - START).days / 30.44)
    avg_month = (bal - INITIAL) / months
    pos_months = sum(1 for v in monthly.values() if v > 0)
    return {
        "net": bal - INITIAL,
        "bal": bal,
        "trades": len(pnls),
        "avg_month": avg_month,
        "pos_months": pos_months,
        "n_months": len(monthly),
        "max_dd_eq_pct": 100.0 * max_dd_eq / max(peak_eq, 1),
        "max_dd_from_init_pct": 100.0 * max_dd_from_init / INITIAL,
        "min_eq": min_eq,
        "day_breach": day_breach,
        "max_breach": max_breach,
        "first_10": first_10,
        "first_15": first_15,
        "wr": 100.0 * sum(1 for x in pnls if x > 0) / len(pnls) if pnls else 0.0,
    }


def main():
    rows = download()
    lines = []
    lines.append("RAPPORT FTMO 100k — depuis 2020 (GoldFTMO v6.2 EMA+pause)")
    lines.append(f"Donnees or: {rows[0][0]} -> {rows[-1][0]}")
    lines.append("Perte max = pire equity FLOTTANTE incluse (plus bas pendant le trade).")
    lines.append("")

    # Calibrate note: MT5 user got ~18341 @1% without new filters.
    # We also scale monthly from user MT5 if sim differs.
    for risk in (0.01, 0.015):
        r = run(rows, risk)
        c = r["cont"]
        lines.append(f"========== RISQUE {risk*100:.1f}% ==========")
        lines.append(f"Trades: {c['trades']} | WR: {c['wr']:.0f}%")
        lines.append(f"Net 2020->aujourd'hui: {c['net']:+.0f} $  (solde {c['bal']:.0f})")
        lines.append(f"Gain moyen / mois: {c['avg_month']:+.0f} $")
        lines.append(f"Mois positifs: {c['pos_months']}/{c['n_months']}")
        lines.append("")
        lines.append("MAX PERTE (avec flottant):")
        lines.append(f"  Pire equity vs pic:     {c['max_dd_eq_pct']:.2f}%")
        lines.append(f"  Pire equity vs depart:  {c['max_dd_from_init_pct']:.2f}%")
        lines.append(f"  Equity mini:            {c['min_eq']:.0f} $")
        lines.append(f"  Breach jour 5%:         {'OUI' if c['day_breach'] else 'NON'}")
        lines.append(f"  Breach total 10%:       {'OUI' if c['max_breach'] else 'NON'}")
        ftmo_ok = (not c["day_breach"]) and (not c["max_breach"]) and c["max_dd_from_init_pct"] <= 10.0
        lines.append(f"  Verdict FTMO pertes:    {'OK' if ftmo_ok else 'ECHEC'}")
        lines.append("")
        lines.append("PASSAGE 2 STEPS (compte separe a chaque phase):")
        lines.append(f"  Phase 1 (+10%): {r['phase1'] or 'pas encore'}")
        lines.append(f"  Phase 2 (+5%):  {r['phase2'] or 'pas encore'}")
        if r["phase1"] and r["phase2"]:
            lines.append(f"  Finance le: {r['phase2']}")
        lines.append("")
        lines.append("Sur un seul compte continu (info):")
        lines.append(f"  Atteint +10%: {c['first_10']}")
        lines.append(f"  Atteint +15%: {c['first_15']}")
        lines.append("")

    lines.append("========== CALIBRAGE AVEC TON MT5 ==========")
    lines.append("Ton test MT5 @1% (sans ces filtres): +18342$ ~ 237$/mois | DD equity 2.89%")
    lines.append("Ton test MT5 @4.5%: DD 16% = ECHEC")
    lines.append("Formule pratique retenue:")
    lines.append("  risque = 1.0%  => ~200 a 250 $/mois sur 100k (ordre de grandeur MT5)")
    lines.append("  risque = 1.5%  => ~300 a 370 $/mois estime, DD a surveiller <10%")
    lines.append("  500$/mois sur 100k: non garanti a risque safe; viser 200k @1% ou accepter ~250$/mois")
    lines.append("")
    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
