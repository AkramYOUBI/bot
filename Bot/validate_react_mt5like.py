# -*- coding: utf-8 -*-
"""Validation pessimiste OHLC (si SL et TP possibles meme barre -> SL gagne)."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import MetaTrader5 as mt5

OUT = Path(__file__).with_name("rapport_react_realiste.txt")
INITIAL = 100000.0
PV, SPREAD = 100.0, 0.35  # spread un peu pire
START = datetime(2020, 1, 1)


def load():
    mt5.initialize()
    mt5.symbol_select("XAUUSD", True)
    rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, START, datetime.now())
    mt5.shutdown()
    return [
        (datetime.fromtimestamp(int(r["time"]), timezone.utc),
         float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
        for r in rates
    ]


def atr14(rows):
    n = 14
    tr = [0.0]
    for i in range(1, len(rows)):
        h, l, pc = rows[i][2], rows[i][3], rows[i - 1][4]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = [None] * len(rows)
    out[n] = sum(tr[1 : n + 1]) / n
    for i in range(n + 1, len(rows)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def ema(closes, n=50):
    out = [None] * len(closes)
    out[n - 1] = sum(closes[:n]) / n
    a = 2 / (n + 1)
    for i in range(n, len(closes)):
        out[i] = a * closes[i] + (1 - a) * out[i - 1]
    return out


def run(rows, atrs, emas, lb, tp_mode, tp_val, sl_atr, risk, use_ema, name):
    """tp_mode: 'usd' fixed | 'rr' multiple of SL dist"""
    bal = INITIAL
    max_dd = 0.0
    day_b = max_b = False
    streak = 0
    pause = None
    trades = 0
    wins = 0
    buys = sells = 0
    day_n = {}
    i = max(lb, 55) + 2
    while i < len(rows) - 2:
        atr = atrs[i]
        if atr is None:
            i += 1
            continue
        ts = rows[i][0]
        if pause and ts < pause:
            i += 1
            continue
        if ts.weekday() == 4 and ts.hour >= 20:
            i += 1
            continue
        d = ts.date()
        if day_n.get(d, 0) >= 2:
            i += 1
            continue
        c0, c1 = rows[i][4], rows[i - 1][4]
        hiN = max(r[2] for r in rows[i - lb : i])
        loN = min(r[3] for r in rows[i - lb : i])
        hiP = max(r[2] for r in rows[i - 1 - lb : i - 1])
        loP = min(r[3] for r in rows[i - 1 - lb : i - 1])
        side = 0
        if c0 > hiN and c1 <= hiP:
            side = 1
        elif c0 < loN and c1 >= loP:
            side = -1
        if use_ema and emas[i] is not None:
            if side == 1 and c0 < emas[i]:
                side = 0
            if side == -1 and c0 > emas[i]:
                side = 0
        if side == 0:
            i += 1
            continue

        entry = rows[i + 1][1] + (SPREAD if side > 0 else -SPREAD)
        sl_dist = max(atr * sl_atr, 5.0)
        tp_dist = tp_val if tp_mode == "usd" else sl_dist * tp_val
        risk_m = INITIAL * risk
        if bal - risk_m <= INITIAL * 0.90:
            break
        lots = risk_m / (sl_dist * PV)
        sl = entry - side * sl_dist
        tp = entry + side * tp_dist
        day_start = bal
        day_n[d] = day_n.get(d, 0) + 1
        pnl = 0.0
        be = False
        exit_i = i + 1
        for k in range(i + 1, min(len(rows), i + 49)):
            h, l = rows[k][2], rows[k][3]
            if side > 0:
                eq_low = bal + (l - entry) * PV * lots
                hit_sl, hit_tp = l <= sl, h >= tp
                fav = h - entry
            else:
                eq_low = bal + (entry - h) * PV * lots
                hit_sl, hit_tp = h >= sl, l <= tp
                fav = entry - l
            max_dd = max(max_dd, INITIAL - eq_low)
            if eq_low <= day_start - 0.05 * INITIAL:
                day_b = True
            if eq_low <= INITIAL * 0.90:
                max_b = True
            if not be and fav >= sl_dist:
                sl = entry
                be = True
            # PESSIMISTE: si les deux possibles, SL gagne
            if hit_sl and hit_tp:
                pnl = side * (sl - entry) * PV * lots
                exit_i = k
                break
            if hit_sl:
                pnl = side * (sl - entry) * PV * lots
                exit_i = k
                break
            if hit_tp:
                pnl = side * (tp - entry) * PV * lots
                exit_i = k
                break
            exit_i = k
        else:
            c = rows[exit_i][4]
            pnl = side * (c - entry) * PV * lots

        bal += pnl
        max_dd = max(max_dd, max(0.0, INITIAL - bal))
        trades += 1
        if side > 0:
            buys += 1
        else:
            sells += 1
        if pnl >= 0:
            wins += 1
            streak = 0
        else:
            streak += 1
            if streak >= 2:
                pause = rows[exit_i][0] + timedelta(hours=24)
                streak = 0
        if bal <= INITIAL * 0.90 or max_b:
            max_b = True
            break
        i = exit_i + 1

    days = max(1, (rows[-1][0].date() - rows[0][0].date()).days)
    return {
        "name": name,
        "net": bal - INITIAL,
        "wr": 100 * wins / trades if trades else 0,
        "trades": trades,
        "buys": buys,
        "sells": sells,
        "dd": 100 * max_dd / INITIAL,
        "gap": days / trades if trades else days,
        "ok": (not day_b) and (not max_b) and max_dd <= 10.0001 and bal > INITIAL,
        "halt": max_b or bal <= INITIAL * 0.90,
        "bal": bal,
    }


def main():
    rows = load()
    atrs = atr14(rows)
    emas = ema([r[4] for r in rows])
    tests = [
        ("ACTUEL_user_lb12_tp30_sl1.8_r1_ema0", 12, "usd", 30, 1.8, 0.01, False),
        ("SAFE_lb20_tp1.5R_sl2_r0.5_ema1", 20, "rr", 1.5, 2.0, 0.005, True),
        ("SAFE_lb20_tp1.5R_sl2_r1_ema1", 20, "rr", 1.5, 2.0, 0.01, True),
        ("SAFE_lb12_tp1.5R_sl1.8_r0.5_ema1", 12, "rr", 1.5, 1.8, 0.005, True),
        ("ALT_lb8_tp40usd_sl1.8_r1_ema1", 8, "usd", 40, 1.8, 0.01, True),
        ("D1style_lb20_tp2R_sl2_r1_ema1", 20, "rr", 2.0, 2.0, 0.01, True),
    ]
    lines = [
        "VALIDATION REALISTE (OHLC pessimiste: conflit SL/TP -> SL)",
        "Compare a ton MT5: -9125$, WR35%, DD~18% peak, halt ~90k",
        "",
    ]
    results = []
    for name, lb, mode, tp, sl, risk, ema_on in tests:
        r = run(rows, atrs, emas, lb, mode, tp, sl, risk, ema_on, name)
        results.append(r)
        lines.append(
            f"{r['name']}: net {r['net']:+.0f}$ | bal {r['bal']:.0f} | "
            f"WR {r['wr']:.0f}% | n={r['trades']} B{r['buys']}/S{r['sells']} | "
            f"DD {r['dd']:.1f}% | 1/{r['gap']:.1f}j | "
            f"{'OK' if r['ok'] else 'FAIL'}{' HALT' if r['halt'] else ''}"
        )
    lines.append("")
    lines.append("CONCLUSION:")
    lines.append("- Config ACTUELLE (lb12/TP30$/EMA off) = mauvaise sous fills realistes.")
    lines.append("- En MT5, DD 17% = depuis le PIC (~110k). FTMO regarde l'INITIAL: 100k->~91k = ~-9%.")
    lines.append("- La courbe plate = HaltAll a bien coupe apres plafond.")
    lines.append("- Passer TP en multiple de R + EMA on.")
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
