# -*- coding: utf-8 -*-
"""
Compare cassure N-barres achat seul sur D1 / H1 / M30 / M15.
Meme risque 1%, plafonds FTMO 5%/10%, 1 position, EMA filtre, pause 2 pertes.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare_tf.txt")
INITIAL = 100000.0
RISK = 0.01
DAILY, MAXLOSS = 0.05, 0.10
ENTRY_N, EXIT_N, ATR_N, SL_ATR = 20, 10, 20, 2.0
PARTIAL_R, PARTIAL_PCT = 1.0, 0.50
LOCK_R, MIN_RR, MAX_BARS = 2.0, 2.0, 15  # max bars on signal TF
EMA, PAUSE_AFTER, PAUSE_BARS = 50, 2, 8
SPREAD = {"1d": 0.40, "1h": 0.35, "30m": 0.35, "15m": 0.40}


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
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(last)


def download(interval: str, days_back: int):
    p2 = int(time.time()) + 86400
    p1 = p2 - days_back * 86400
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
        f"?period1={p1}&period2={p2}&interval={interval}"
    )
    res = http_json(url)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        dt = datetime.fromtimestamp(t, timezone.utc)
        rows.append((dt, float(o), float(h), float(l), float(c)))
    return rows


def atr_wilder(rows, n):
    trs = [0.0]
    for i in range(1, len(rows)):
        _, _, h, l, c = rows[i]
        pc = rows[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = [None] * len(rows)
    if len(rows) <= n:
        return out
    out[n] = sum(trs[1 : n + 1]) / n
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


def simulate(rows, interval: str):
    spread = SPREAD.get(interval, 0.35)
    closes = [r[4] for r in rows]
    atrs = atr_wilder(rows, ATR_N)
    emas = ema(closes, EMA)
    bal = INITIAL
    peak = INITIAL
    max_dd = 0.0
    max_dd_init = 0.0
    day_breach = max_breach = False
    streak = 0
    pause_until = -1
    holds = []
    trades = 0
    wins = 0
    # trades per calendar day
    by_day = {}
    i = ENTRY_N + EMA + 5
    while i < len(rows) - 2:
        atr = atrs[i]
        if atr is None or atr <= 0:
            i += 1
            continue
        if i < pause_until:
            i += 1
            continue
        hh = max(rows[j][2] for j in range(i - ENTRY_N, i))
        hh_prev = max(rows[j][2] for j in range(i - 1 - ENTRY_N, i - 1))
        if not (rows[i][4] > hh and rows[i - 1][4] <= hh_prev):
            i += 1
            continue
        if emas[i] is None or rows[i][4] < emas[i] or emas[i] <= emas[i - 3]:
            i += 1
            continue

        entry = rows[i + 1][1] + spread
        dist = atr * SL_ATR
        if dist <= 0:
            i += 1
            continue
        lots = (INITIAL * RISK) / (dist * 100.0)
        day_start = bal
        if bal - INITIAL * RISK <= day_start - DAILY * INITIAL:
            i += 1
            continue
        if bal - INITIAL * RISK <= INITIAL * (1 - MAXLOSS):
            i += 1
            continue

        sl = entry - dist
        tp = entry + dist * MIN_RR
        partial = False
        pk = entry
        vol = lots
        pnl = 0.0
        entry_i = i + 1
        exit_i = entry_i
        ed = rows[entry_i][0].date()
        by_day[ed] = by_day.get(ed, 0) + 1

        for k in range(entry_i, min(len(rows), entry_i + MAX_BARS + 1)):
            hk, lk, ck = rows[k][2], rows[k][3], rows[k][4]
            eq = bal + (lk - entry) * 100.0 * vol
            peak = max(peak, bal + (hk - entry) * 100.0 * vol)
            max_dd = max(max_dd, peak - eq)
            max_dd_init = max(max_dd_init, INITIAL - eq)
            if eq <= day_start - DAILY * INITIAL:
                day_breach = True
            if eq <= INITIAL * (1 - MAXLOSS):
                max_breach = True

            if lk <= sl:
                pnl += (sl - entry) * 100.0 * vol
                vol = 0
                exit_i = k
                break
            pk = max(pk, hk)
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
                nsl = pk - dist
                if partial:
                    nsl = max(nsl, entry)
                sl = max(sl, nsl)
            if hk >= tp:
                pnl += (tp - entry) * 100.0 * vol
                vol = 0
                exit_i = k
                break
            if k >= entry_i + 1:
                elow = min(rows[j][3] for j in range(k - EXIT_N, k))
                if ck < elow:
                    pnl += (ck - spread - entry) * 100.0 * vol
                    vol = 0
                    exit_i = k
                    break
            if k - entry_i >= MAX_BARS:
                pnl += (ck - spread - entry) * 100.0 * vol
                vol = 0
                exit_i = k
                break
            exit_i = k

        if vol > 0:
            pnl += (rows[exit_i][4] - entry) * 100.0 * vol
        bal += pnl
        peak = max(peak, bal)
        max_dd = max(max_dd, peak - bal)
        max_dd_init = max(max_dd_init, max(0.0, INITIAL - bal))
        holds.append(exit_i - entry_i)
        trades += 1
        if pnl >= 0:
            wins += 1
            streak = 0
        else:
            streak += 1
            if streak >= PAUSE_AFTER:
                pause_until = exit_i + PAUSE_BARS
                streak = 0
        if bal <= INITIAL * (1 - MAXLOSS):
            max_breach = True
            break
        i = exit_i + 1

    days = max(1, (rows[-1][0].date() - rows[0][0].date()).days)
    months = days / 30.44
    active_days = len(by_day)
    multi = sum(1 for v in by_day.values() if v > 1)
    # average gap between trades in calendar days
    if trades >= 2:
        # approximate: days/trades
        gap = days / trades
    else:
        gap = days
    holds_s = sorted(holds) if holds else [0]
    return {
        "interval": interval,
        "bars": len(rows),
        "from": rows[0][0],
        "to": rows[-1][0],
        "days": days,
        "trades": trades,
        "wr": 100.0 * wins / trades if trades else 0,
        "net": bal - INITIAL,
        "month": (bal - INITIAL) / months if months else 0,
        "trades_per_day": trades / days,
        "gap_days": gap,
        "days_with_trade": active_days,
        "days_multi": multi,
        "hold_min": holds_s[0],
        "hold_med": holds_s[len(holds_s) // 2],
        "hold_max": holds_s[-1],
        "dd_peak": 100.0 * max_dd / max(peak, 1),
        "dd_init": 100.0 * max_dd_init / INITIAL,
        "ok": (not day_breach) and (not max_breach) and max_dd_init <= 10.0,
    }


def main():
    specs = [
        ("1d", 2500),
        ("1h", 700),
        ("30m", 60),   # yahoo short history
        ("15m", 60),
    ]
    lines = []
    lines.append("COMPARAISON TIMEFRAMES — meme logique FTMO (risque 1%, 1 position)")
    lines.append("Objectif: viser ~1 trade / 1-2 jours sans bruler 5%/10%")
    lines.append("")
    results = []
    for interval, days in specs:
        try:
            rows = download(interval, days)
            if len(rows) < 200:
                lines.append(f"{interval}: pas assez de barres ({len(rows)})")
                continue
            r = simulate(rows, interval)
            results.append(r)
            lines.append(f"=== {interval} | {r['from']} -> {r['to']} | {r['bars']} barres ===")
            lines.append(f"  Trades: {r['trades']} | WR {r['wr']:.0f}% | net {r['net']:+.0f}$ | ~/mois {r['month']:+.0f}$")
            lines.append(f"  Rythme: {r['trades_per_day']:.2f} trade/jour | 1 trade tous les ~{r['gap_days']:.1f} jours")
            lines.append(f"  Jours avec trade: {r['days_with_trade']} | jours >1 trade: {r['days_multi']}")
            lines.append(f"  Duree (barres TF): min {r['hold_min']} | med {r['hold_med']} | max {r['hold_max']}")
            lines.append(f"  DD pic {r['dd_peak']:.1f}% | DD init {r['dd_init']:.1f}% | FTMO pertes: {'OK' if r['ok'] else 'ECHEC'}")
            lines.append("")
        except Exception as e:
            lines.append(f"{interval}: ERREUR {e}")
            lines.append("")

    lines.append("=== VERDICT ===")
    lines.append("D1: trop lent pour 1 trade/1-2j")
    lines.append("H1: meilleur candidat pour densifier sans scalping extrême")
    lines.append("M15/M30: plus de trades, plus de spread/bruit — DD souvent pire")
    lines.append("Regle: 1 position max + risque 1% => meme si 1 trade/jour, 1 perte/jour = 1% << 5%")
    lines.append("Danger: enchaine plusieurs pertes/semaine => grignote les 10%")
    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
