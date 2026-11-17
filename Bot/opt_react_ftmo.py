# -*- coding: utf-8 -*-
"""Optimisation rapide buy+sell H1 reactive sous FTMO."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import MetaTrader5 as mt5

OUT = Path(__file__).with_name("rapport_react_2020.txt")
INITIAL = 100000.0
DAILY, MAXLOSS = 0.05, 0.10
PV, SPREAD = 100.0, 0.30
START = datetime(2020, 1, 1)


def load():
    assert mt5.initialize()
    mt5.symbol_select("XAUUSD", True)
    rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, START, datetime.now())
    mt5.shutdown()
    return [
        (
            datetime.fromtimestamp(int(r["time"]), timezone.utc),
            float(r["open"]),
            float(r["high"]),
            float(r["low"]),
            float(r["close"]),
        )
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


def ema50(closes):
    n = 50
    out = [None] * len(closes)
    out[n - 1] = sum(closes[:n]) / n
    a = 2 / (n + 1)
    for i in range(n, len(closes)):
        out[i] = a * closes[i] + (1 - a) * out[i - 1]
    return out


def pivots(rows, wing=2):
    hi, lo = [], []
    for i in range(wing, len(rows) - wing):
        h, l = rows[i][2], rows[i][3]
        if all(h >= rows[i - k][2] and h >= rows[i + k][2] for k in range(1, wing + 1)):
            hi.append((i, h))
        if all(l <= rows[i - k][3] and l <= rows[i + k][3] for k in range(1, wing + 1)):
            lo.append((i, l))
    return hi, lo


def sim(rows, atrs, emas, phi, plo, mode, lb, tp, sl_atr, risk, use_ema, max_day=2):
    bal = INITIAL
    max_dd = 0.0
    day_b = max_b = False
    streak = 0
    pause = None
    trades = []
    day_n = {}
    i = max(lb, 55) + 2
    phi_i = 0
    plo_i = 0
    last_res = last_sup = None

    while i < len(rows) - 2:
        atr = atrs[i]
        if atr is None or atr < 0.8:
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
        if day_n.get(d, 0) >= max_day:
            i += 1
            continue

        while phi_i < len(phi) and phi[phi_i][0] < i - 2:
            last_res = phi[phi_i][1]
            phi_i += 1
        while plo_i < len(plo) and plo[plo_i][0] < i - 2:
            last_sup = plo[plo_i][1]
            plo_i += 1

        c0, c1 = rows[i][4], rows[i - 1][4]
        hiN = max(r[2] for r in rows[i - lb : i])
        loN = min(r[3] for r in rows[i - lb : i])
        hiP = max(r[2] for r in rows[i - 1 - lb : i - 1])
        loP = min(r[3] for r in rows[i - 1 - lb : i - 1])
        side = 0

        if mode == "breakout":
            if c0 > hiN and c1 <= hiP:
                side = 1
            elif c0 < loN and c1 >= loP:
                side = -1
            if use_ema and emas[i] is not None:
                if side == 1 and c0 < emas[i]:
                    side = 0
                if side == -1 and c0 > emas[i]:
                    side = 0
        else:
            z = max(atr * 0.25, 0.8)
            if last_res is not None and rows[i][2] >= last_res - z and c0 < min(last_res, rows[i][1]):
                side = -1
            elif last_sup is not None and rows[i][3] <= last_sup + z and c0 > max(last_sup, rows[i][1]):
                side = 1
            if use_ema and emas[i] is not None and side != 0:
                if side == 1 and c0 < emas[i]:
                    side = 0
                if side == -1 and c0 > emas[i]:
                    side = 0

        if side == 0:
            i += 1
            continue

        entry = rows[i + 1][1] + (SPREAD if side > 0 else -SPREAD)
        sl_dist = max(atr * sl_atr, tp * 0.6)
        risk_m = INITIAL * risk
        if bal - risk_m <= INITIAL * (1 - MAXLOSS):
            break
        lots = risk_m / (sl_dist * PV)
        sl = entry - side * sl_dist
        tp_px = entry + side * tp
        day_start = bal
        day_n[d] = day_n.get(d, 0) + 1
        pnl = 0.0
        be = False
        exit_i = i + 1

        for k in range(i + 1, min(len(rows), i + 49)):
            h, l = rows[k][2], rows[k][3]
            if side > 0:
                eq_low = bal + (l - entry) * PV * lots
                hit_sl, hit_tp = l <= sl, h >= tp_px
                fav = h - entry
            else:
                eq_low = bal + (entry - h) * PV * lots
                hit_sl, hit_tp = h >= sl, l <= tp_px
                fav = entry - l
            max_dd = max(max_dd, INITIAL - eq_low)
            if eq_low <= day_start - DAILY * INITIAL:
                day_b = True
            if eq_low <= INITIAL * (1 - MAXLOSS):
                max_b = True
            if not be and fav >= sl_dist:
                sl = entry
                be = True
            if hit_sl:
                pnl = side * (sl - entry) * PV * lots
                exit_i = k
                break
            if hit_tp:
                pnl = side * (tp_px - entry) * PV * lots
                exit_i = k
                break
            exit_i = k
        else:
            c = rows[exit_i][4]
            pnl = side * (c - entry) * PV * lots

        bal += pnl
        max_dd = max(max_dd, max(0.0, INITIAL - bal))
        win = pnl >= 0
        trades.append((ts, pnl, win, side))
        if win:
            streak = 0
        else:
            streak += 1
            if streak >= 2:
                pause = rows[exit_i][0] + timedelta(hours=24)
                streak = 0
        if bal <= INITIAL * (1 - MAXLOSS) or max_b:
            max_b = True
            break
        i = exit_i + 1

    days = max(1, (rows[-1][0].date() - rows[0][0].date()).days)
    n = len(trades)
    wins = sum(1 for t in trades if t[2])
    net = bal - INITIAL
    bal_r = INITIAL
    t10 = None
    for t in trades:
        bal_r += t[1]
        if t10 is None and bal_r >= INITIAL * 1.1:
            t10 = t[0]
    loss_ok = (not day_b) and (not max_b) and max_dd <= INITIAL * 0.10 + 1e-6
    return {
        "net": net,
        "month": net / (days / 30.44),
        "trades": n,
        "wr": 100 * wins / n if n else 0,
        "gap": days / n if n else days,
        "dd": 100 * max_dd / INITIAL,
        "loss_ok": loss_ok,
        "ok": loss_ok and net > 0,
        "t10": t10,
        "buys": sum(1 for t in trades if t[3] > 0),
        "sells": sum(1 for t in trades if t[3] < 0),
        "day_b": day_b,
        "max_b": max_b,
    }


def main():
    print("load H1...")
    rows = load()
    print(f"bars={len(rows)}")
    atrs = atr14(rows)
    emas = ema50([r[4] for r in rows])
    phi, plo = pivots(rows, 2)

    grid = []
    for mode in ("breakout", "bounce"):
        for lb in (8, 12, 16):
            for tp in (30.0, 40.0, 50.0):
                for sl_atr in (1.2, 1.8):
                    for risk in (0.005, 0.01):
                        for use_ema in (True, False):
                            if mode == "bounce" and not use_ema:
                                continue
                            grid.append((mode, lb, tp, sl_atr, risk, use_ema))

    print(f"configs={len(grid)}")
    results = []
    for idx, (mode, lb, tp, sl_atr, risk, use_ema) in enumerate(grid, 1):
        name = f"{mode}_lb{lb}_tp{tp:.0f}_sl{sl_atr}_r{risk*100:.1f}_ema{int(use_ema)}"
        r = sim(rows, atrs, emas, phi, plo, mode, lb, tp, sl_atr, risk, use_ema)
        r["name"] = name
        results.append(r)
        if idx % 20 == 0:
            print(f"  {idx}/{len(grid)}...")

    results.sort(key=lambda r: (r["ok"], r["loss_ok"], r["net"]), reverse=True)

    lines = [
        "RAPPORT BUY+SELL REACTIF — XAUUSD H1 depuis 2020 (MT5)",
        "FTMO: -5% jour / -10% total | risque fixe sur capital INITIAL | 1 position",
        "",
        "PHOTO +13M$ / WR93% / DD$284k:",
        "  NON reproductible sous FTMO (levier/compounding + profil martingale).",
        "  Objectif ici = meilleur net REALISTE avec plafonds respectes.",
        "",
        f"Configs: {len(results)} | OK+profit: {sum(1 for r in results if r['ok'])}",
        "",
        "=== TOP 12 ===",
    ]
    for r in results[:12]:
        lines.append(
            f"{r['name']}: net {r['net']:+.0f}$ | ~/m {r['month']:+.0f}$ | "
            f"n={r['trades']} B{r['buys']}/S{r['sells']} | WR {r['wr']:.0f}% | "
            f"1/{r['gap']:.1f}j | DD {r['dd']:.1f}% | "
            f"{'OK' if r['loss_ok'] else 'FAIL'} | "
            f"+10% {r['t10'].date() if r['t10'] else '-'}"
        )

    best = next((r for r in results if r["ok"]), None)
    lines.append("")
    if best:
        lines.append(f"RETENU POUR L'EA: {best['name']}")
        lines.append(
            f"  net {best['net']:+.0f}$ | WR {best['wr']:.0f}% | "
            f"1 trade / {best['gap']:.1f}j | DD {best['dd']:.1f}% | "
            f"buys {best['buys']} sells {best['sells']}"
        )
    else:
        best = results[0]
        lines.append(f"Aucun OK+profit. Meilleur compromis: {best['name']} net {best['net']:+.0f}$")

    dens = [r for r in results if r["ok"] and r["gap"] <= 3]
    lines.append("")
    lines.append(f"OK+profit et <=1 trade/3j: {len(dens)}")
    for r in dens[:5]:
        lines.append(f"  {r['name']}: 1/{r['gap']:.1f}j net {r['net']:+.0f}$ DD {r['dd']:.1f}%")

    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
