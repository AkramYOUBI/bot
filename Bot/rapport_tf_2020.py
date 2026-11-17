# -*- coding: utf-8 -*-
"""
Rapport TF courts depuis 2020 — meme logique GoldFTMO v6.3
Achat seul, cassure N, EMA, pause 2 pertes, risque 1%, plafonds 5%/10%.
Donnees : MT5 XAUUSD.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5

OUT = Path(__file__).with_name("rapport_tf_2020.txt")
INITIAL = 100000.0
RISK = 0.01
DAILY, MAXLOSS = 0.05, 0.10
ENTRY_N, EXIT_N, ATR_N, SL_ATR = 20, 10, 20, 2.0
PARTIAL_R, PARTIAL_PCT = 1.0, 0.50
LOCK_R, MIN_RR = 2.0, 2.0
EMA_N, PAUSE_AFTER, PAUSE_DAYS = 50, 2, 8
MAX_HOLD_DAYS = 15
SPREAD = 0.35  # $ approx
START = datetime(2020, 1, 1)
POINT_VALUE = 100.0  # 1 lot XAU ~ 100$ / $ de mouvement


def load_rates(tf, start=START):
    rates = mt5.copy_rates_range("XAUUSD", tf, start, datetime.now())
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"Pas de data TF={tf}: {mt5.last_error()}")
    rows = []
    for r in rates:
        dt = datetime.fromtimestamp(int(r["time"]), timezone.utc)
        rows.append((dt, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return rows


def atr_wilder(rows, n):
    trs = [0.0]
    for i in range(1, len(rows)):
        _, _, h, l, _ = rows[i]
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


def simulate(rows, name: str):
    closes = [r[4] for r in rows]
    atrs = atr_wilder(rows, ATR_N)
    emas = ema(closes, EMA_N)

    bal = INITIAL
    peak = INITIAL
    max_dd_peak = 0.0
    max_dd_init = 0.0
    day_breach = False
    max_breach = False
    streak = 0
    pause_until_ts = None

    trades = []
    by_day = {}
    by_year = {}
    monthly = {}
    float_min = 0.0

    i = ENTRY_N + EMA_N + 5
    while i < len(rows) - 2:
        atr = atrs[i]
        if atr is None or atr <= 0:
            i += 1
            continue

        now = rows[i][0]
        if pause_until_ts and now < pause_until_ts:
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

        entry = rows[i + 1][1] + SPREAD
        dist = atr * SL_ATR
        if dist <= 0:
            i += 1
            continue

        risk_money = INITIAL * RISK
        lots = risk_money / (dist * POINT_VALUE)
        if lots <= 0:
            i += 1
            continue

        # plafond avant entree
        day_key = now.date()
        # approx day floor: balance at day start unknown -> use bal
        if bal - risk_money <= INITIAL * (1 - MAXLOSS):
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
        open_ts = rows[entry_i][0]
        day_start_bal = bal
        max_hold_bars = None
        # convert 15 calendar days to bars approx from TF spacing
        # better: exit when calendar days >= MAX_HOLD_DAYS

        by_day[day_key] = by_day.get(day_key, 0) + 1

        for k in range(entry_i, len(rows)):
            hk, lk, ck = rows[k][2], rows[k][3], rows[k][4]
            ts = rows[k][0]
            # floating equity worst (low)
            eq_low = bal + (lk - entry) * POINT_VALUE * vol + pnl
            eq_high = bal + (hk - entry) * POINT_VALUE * vol + pnl
            peak = max(peak, eq_high)
            max_dd_peak = max(max_dd_peak, peak - eq_low)
            max_dd_init = max(max_dd_init, INITIAL - eq_low)
            float_min = min(float_min, eq_low - INITIAL)
            if eq_low <= day_start_bal - DAILY * INITIAL:
                day_breach = True
            if eq_low <= INITIAL * (1 - MAXLOSS):
                max_breach = True

            if lk <= sl:
                pnl += (sl - entry) * POINT_VALUE * vol
                vol = 0.0
                exit_i = k
                break

            pk = max(pk, hk)
            gain = hk - entry
            if not partial and gain >= dist * PARTIAL_R:
                cv = vol * PARTIAL_PCT
                pnl += dist * PARTIAL_R * POINT_VALUE * cv
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
                pnl += (tp - entry) * POINT_VALUE * vol
                vol = 0.0
                exit_i = k
                break

            if k >= entry_i + 1:
                elow = min(rows[j][3] for j in range(max(0, k - EXIT_N), k))
                if ck < elow:
                    pnl += (ck - SPREAD - entry) * POINT_VALUE * vol
                    vol = 0.0
                    exit_i = k
                    break

            hold_days = (ts - open_ts).total_seconds() / 86400.0
            if hold_days >= MAX_HOLD_DAYS:
                pnl += (ck - SPREAD - entry) * POINT_VALUE * vol
                vol = 0.0
                exit_i = k
                break
            exit_i = k

        if vol > 0:
            pnl += (rows[exit_i][4] - entry) * POINT_VALUE * vol

        bal += pnl
        peak = max(peak, bal)
        max_dd_peak = max(max_dd_peak, peak - bal)
        max_dd_init = max(max_dd_init, max(0.0, INITIAL - bal))

        hold_h = (rows[exit_i][0] - open_ts).total_seconds() / 3600.0
        win = pnl >= 0
        y = open_ts.year
        by_year.setdefault(y, {"n": 0, "pnl": 0.0, "w": 0})
        by_year[y]["n"] += 1
        by_year[y]["pnl"] += pnl
        if win:
            by_year[y]["w"] += 1
        mk = f"{open_ts.year}-{open_ts.month:02d}"
        monthly[mk] = monthly.get(mk, 0.0) + pnl

        trades.append(
            {
                "pnl": pnl,
                "hold_h": hold_h,
                "win": win,
                "open": open_ts,
                "close": rows[exit_i][0],
            }
        )

        if win:
            streak = 0
        else:
            streak += 1
            if streak >= PAUSE_AFTER:
                # pause PAUSE_DAYS calendar days after exit
                pause_until_ts = rows[exit_i][0].replace(tzinfo=timezone.utc)
                from datetime import timedelta

                pause_until_ts = rows[exit_i][0] + timedelta(days=PAUSE_DAYS)
                streak = 0

        if bal <= INITIAL * (1 - MAXLOSS):
            max_breach = True
            break

        i = exit_i + 1

    days = max(1, (rows[-1][0].date() - rows[0][0].date()).days)
    months = days / 30.44
    n = len(trades)
    wins = sum(1 for t in trades if t["win"])
    holds = sorted(t["hold_h"] for t in trades) if trades else [0]
    pnls = [t["pnl"] for t in trades]
    gap = days / n if n else days
    # months with positive pnl
    pos_m = sum(1 for v in monthly.values() if v > 0)
    neg_m = sum(1 for v in monthly.values() if v <= 0)

    # first time +10% / challenge-ish
    bal_run = INITIAL
    t_pass10 = None
    for t in trades:
        bal_run += t["pnl"]
        if t_pass10 is None and bal_run >= INITIAL * 1.10:
            t_pass10 = t["close"]

    return {
        "name": name,
        "bars": len(rows),
        "from": rows[0][0],
        "to": rows[-1][0],
        "days": days,
        "trades": n,
        "wr": 100.0 * wins / n if n else 0.0,
        "net": bal - INITIAL,
        "bal": bal,
        "month_avg": (bal - INITIAL) / months if months else 0.0,
        "gap_days": gap,
        "trades_per_day": n / days,
        "days_with_trade": len(by_day),
        "days_multi": sum(1 for v in by_day.values() if v > 1),
        "hold_min_h": holds[0],
        "hold_med_h": holds[len(holds) // 2],
        "hold_max_h": holds[-1],
        "dd_peak_pct": 100.0 * max_dd_peak / max(peak, 1),
        "dd_init_pct": 100.0 * max_dd_init / INITIAL,
        "float_min": float_min,
        "day_breach": day_breach,
        "max_breach": max_breach,
        "ok_loss": (not day_breach) and (not max_breach) and max_dd_init <= INITIAL * 0.10 + 1e-6,
        "by_year": by_year,
        "pos_months": pos_m,
        "neg_months": neg_m,
        "t_pass10": t_pass10,
        "avg_win": (sum(p for p in pnls if p >= 0) / max(1, wins)) if n else 0,
        "avg_loss": (sum(p for p in pnls if p < 0) / max(1, n - wins)) if n else 0,
    }


def fmt(r):
    lines = []
    lines.append(f"=== {r['name']} | {r['from'].date()} -> {r['to'].date()} | {r['bars']} barres ===")
    lines.append(
        f"  Trades: {r['trades']} | WR {r['wr']:.0f}% | "
        f"gain moy {r['avg_win']:+.0f}$ | perte moy {r['avg_loss']:+.0f}$"
    )
    lines.append(
        f"  Net depuis 2020: {r['net']:+.0f}$ (solde {r['bal']:.0f}) | "
        f"~/mois {r['month_avg']:+.0f}$"
    )
    lines.append(
        f"  Rythme: {r['trades_per_day']:.2f} trade/jour | "
        f"1 trade tous les ~{r['gap_days']:.1f} jours"
    )
    lines.append(
        f"  Jours avec trade: {r['days_with_trade']} | jours >1 trade: {r['days_multi']}"
    )
    lines.append(
        f"  Duree: min {r['hold_min_h']:.1f}h | med {r['hold_med_h']:.1f}h | "
        f"max {r['hold_max_h']:.1f}h"
    )
    lines.append(
        f"  DD pic {r['dd_peak_pct']:.1f}% | DD vs capital {r['dd_init_pct']:.1f}% | "
        f"pire flottant {r['float_min']:+.0f}$"
    )
    lines.append(
        f"  Plafond jour touche: {'OUI' if r['day_breach'] else 'non'} | "
        f"plafond -10%: {'OUI' if r['max_breach'] else 'non'} | "
        f"FTMO pertes: {'OK' if r['ok_loss'] else 'ECHEC'}"
    )
    if r["t_pass10"]:
        lines.append(f"  Premier +10% (challenge step1): {r['t_pass10'].date()}")
    else:
        lines.append("  Premier +10%: jamais atteint sur la periode")
    lines.append("  Par annee:")
    for y in sorted(r["by_year"]):
        yinfo = r["by_year"][y]
        wr = 100.0 * yinfo["w"] / yinfo["n"] if yinfo["n"] else 0
        lines.append(
            f"    {y}: {yinfo['n']} trades | WR {wr:.0f}% | PnL {yinfo['pnl']:+.0f}$"
        )
    lines.append(
        f"  Mois +: {r['pos_months']} | mois -: {r['neg_months']}"
    )
    lines.append("")
    return "\n".join(lines)


def main():
    if not mt5.initialize():
        raise SystemExit(f"MT5 init fail: {mt5.last_error()}")
    if not mt5.symbol_select("XAUUSD", True):
        raise SystemExit("XAUUSD introuvable")

    specs = [
        ("D1 (reference)", mt5.TIMEFRAME_D1),
        ("H1 (densifie)", mt5.TIMEFRAME_H1),
        ("M30", mt5.TIMEFRAME_M30),
        ("M15", mt5.TIMEFRAME_M15),
    ]

    lines = []
    lines.append("RAPPORT TF COURTS — depuis 2020 (GoldFTMO v6.3 logique)")
    lines.append("Compte 100k | risque 1% | 1 position | EMA50 + pause 2 pertes / 8j")
    lines.append("Cassure 20 / sortie 10 / SL 2 ATR / partielle 1R 50% / lock 2R / TP 2R mini")
    lines.append("Source: MetaTrader5 XAUUSD (pas Yahoo)")
    lines.append("")

    results = []
    for name, tf in specs:
        try:
            rows = load_rates(tf)
            # clip to 2020+
            rows = [r for r in rows if r[0].replace(tzinfo=None) >= START]
            if len(rows) < 300:
                lines.append(f"{name}: pas assez de barres ({len(rows)})")
                continue
            r = simulate(rows, name)
            results.append(r)
            lines.append(fmt(r))
        except Exception as e:
            lines.append(f"{name}: ERREUR {e}\n")

    lines.append("=== VERDICT ===")
    if results:
        best = max(results, key=lambda x: x["net"])
        dens = [r for r in results if r["gap_days"] <= 2.5]
        lines.append(
            f"Meilleur net: {best['name']} ({best['net']:+.0f}$)"
        )
        if dens:
            lines.append(
                "TF proches de 1 trade / 1-2j: "
                + ", ".join(f"{r['name']} (~{r['gap_days']:.1f}j)" for r in dens)
            )
        else:
            lines.append("Aucun TF n'atteint vraiment 1 trade / 1-2 jours ET un net solide.")
        lines.append(
            "Rappel: plus le TF est court, plus le meme N=20 devient 'micro-cassure' "
            "(plus de trades, plus de faux signaux)."
        )
        ok = [r for r in results if r["ok_loss"] and r["net"] > 0]
        if ok:
            lines.append(
                "Sous plafonds pertes FTMO + net > 0: "
                + ", ".join(r["name"] for r in ok)
            )
        else:
            lines.append(
                "Aucun TF court ne combine net > 0 et respect strict des plafonds "
                "sur toute la periode 2020+ (voir DD / breaches)."
            )

    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    mt5.shutdown()


if __name__ == "__main__":
    main()
