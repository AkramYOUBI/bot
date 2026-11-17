# -*- coding: utf-8 -*-
"""Recherche meilleur FTMO 2020+ MT5 — OHLC pessimiste, plafonds durs."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import MetaTrader5 as mt5

OUT = Path(__file__).with_name("rapport_best_ftmo.txt")
INITIAL = 100000.0
PV = 100.0
START = datetime(2020, 1, 1)


def load(tf):
    assert mt5.initialize()
    mt5.symbol_select("XAUUSD", True)
    rates = mt5.copy_rates_range("XAUUSD", tf, START, datetime.now())
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


def atr20(rows):
    n = 20
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


def atr_sma(atrs, i, n=50):
    if i < n or atrs[i] is None:
        return None
    vals = [atrs[j] for j in range(i - n + 1, i + 1) if atrs[j] is not None]
    if len(vals) < n:
        return None
    return sum(vals) / n


def sim(rows, atrs, emas, cfg):
    bal = INITIAL
    max_dd = 0.0
    day_b = max_b = False
    streak = 0
    pause = None
    trades = []
    day_n = {}
    i = max(cfg["en"], 55) + 5

    while i < len(rows) - 2:
        atr = atrs[i]
        if atr is None or atr <= 0:
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
        if day_n.get(d, 0) >= cfg["max_day"]:
            i += 1
            continue
        if cfg["cap"] > 0:
            avg = atr_sma(atrs, i)
            if avg and atr > avg * cfg["cap"]:
                i += 1
                continue

        c0, c1 = rows[i][4], rows[i - 1][4]
        hi = max(r[2] for r in rows[i - cfg["en"] : i])
        hiP = max(r[2] for r in rows[i - 1 - cfg["en"] : i - 1])
        lo = min(r[3] for r in rows[i - cfg["en"] : i])
        loP = min(r[3] for r in rows[i - 1 - cfg["en"] : i - 1])

        side = 0
        if c0 > hi and c1 <= hiP:
            side = 1
        elif cfg["both"] and c0 < lo and c1 >= loP:
            side = -1
        if side == 0:
            i += 1
            continue

        if cfg["ema"] and emas[i] is not None:
            if side > 0 and (c0 < emas[i] or emas[i] <= emas[i - 3]):
                i += 1
                continue
            if side < 0 and (c0 > emas[i] or emas[i] >= emas[i - 3]):
                i += 1
                continue

        sp = cfg["spread"]
        entry = rows[i + 1][1] + (sp if side > 0 else -sp)
        dist = atr * cfg["slatr"]
        risk_m = INITIAL * cfg["risk"]
        if bal - risk_m <= INITIAL * 0.90:
            break
        lots = risk_m / (dist * PV)
        sl = entry - side * dist
        tp = entry + side * dist * cfg["rr"]
        vol = lots
        pnl = 0.0
        part = False
        day_start = bal
        day_n[d] = day_n.get(d, 0) + 1
        open_ts = rows[i + 1][0]
        exit_i = i + 1
        max_bars = int(cfg["hold_days"] * cfg["bpd"]) + 2

        for k in range(i + 1, min(len(rows), i + 1 + max_bars)):
            h, l, c = rows[k][2], rows[k][3], rows[k][4]
            if side > 0:
                eq_low = bal + pnl + (l - entry) * PV * vol
                hit_sl, hit_tp = l <= sl, h >= tp
                fav = h - entry
            else:
                eq_low = bal + pnl + (entry - h) * PV * vol
                hit_sl, hit_tp = h >= sl, l <= tp
                fav = entry - l
            max_dd = max(max_dd, INITIAL - eq_low)
            if eq_low <= day_start - 0.05 * INITIAL:
                day_b = True
            if eq_low <= INITIAL * 0.90:
                max_b = True

            if cfg["partial"] and not part and fav >= dist:
                cut = vol * 0.5
                pnl += side * dist * PV * cut
                vol -= cut
                sl = entry
                part = True
            if cfg["lock"] and fav >= dist * 2:
                sl = entry if side > 0 else entry

            if hit_sl and hit_tp:
                pnl += side * (sl - entry) * PV * vol
                vol = 0
                exit_i = k
                break
            if hit_sl:
                pnl += side * (sl - entry) * PV * vol
                vol = 0
                exit_i = k
                break
            if hit_tp:
                pnl += side * (tp - entry) * PV * vol
                vol = 0
                exit_i = k
                break

            if k >= i + 1 + cfg["ex"]:
                if side > 0:
                    el = min(r[3] for r in rows[k - cfg["ex"] : k])
                    if c < el:
                        pnl += (c - sp - entry) * PV * vol
                        vol = 0
                        exit_i = k
                        break
                else:
                    eh = max(r[2] for r in rows[k - cfg["ex"] : k])
                    if c > eh:
                        pnl += (entry - (c + sp)) * PV * vol
                        vol = 0
                        exit_i = k
                        break

            if (rows[k][0] - open_ts).total_seconds() / 86400.0 >= cfg["hold_days"]:
                if side > 0:
                    pnl += (c - sp - entry) * PV * vol
                else:
                    pnl += (entry - (c + sp)) * PV * vol
                vol = 0
                exit_i = k
                break
            exit_i = k

        if vol > 0:
            c = rows[exit_i][4]
            pnl += side * (c - entry) * PV * vol

        bal += pnl
        max_dd = max(max_dd, max(0.0, INITIAL - bal))
        win = pnl >= 0
        trades.append((open_ts, pnl, win, side))
        if win:
            streak = 0
        else:
            streak += 1
            if streak >= cfg["pause_n"]:
                pause = rows[exit_i][0] + timedelta(days=cfg["pause_d"])
                streak = 0
        if bal <= INITIAL * 0.90 or max_b:
            max_b = True
            break
        i = exit_i + 1

    days = max(1, (rows[-1][0].date() - rows[0][0].date()).days)
    n = len(trades)
    wins = sum(1 for t in trades if t[2])
    net = bal - INITIAL
    run = INITIAL
    t5 = t10 = None
    for t in trades:
        run += t[1]
        if t5 is None and run >= INITIAL * 1.05:
            t5 = t[0]
        if t10 is None and run >= INITIAL * 1.10:
            t10 = t[0]
    loss_ok = (not day_b) and (not max_b) and max_dd <= INITIAL * 0.10 + 1e-6
    return {
        "name": cfg["name"],
        "net": net,
        "month": net / (days / 30.44),
        "trades": n,
        "wr": 100 * wins / n if n else 0,
        "dd": 100 * max_dd / INITIAL,
        "gap": days / n if n else days,
        "loss_ok": loss_ok,
        "ok": loss_ok and net > 0,
        "t5": t5,
        "t10": t10,
        "halt": max_b,
        "buys": sum(1 for t in trades if t[3] > 0),
        "sells": sum(1 for t in trades if t[3] < 0),
    }


def main():
    print("load...")
    d1 = load(mt5.TIMEFRAME_D1)
    h1 = load(mt5.TIMEFRAME_H1)
    d1a, d1e = atr20(d1), ema50([r[4] for r in d1])
    h1a, h1e = atr20(h1), ema50([r[4] for r in h1])
    print(f"D1={len(d1)} H1={len(h1)}")

    jobs = []
    # D1 long — famille GoldFTMO
    for en, ex in ((20, 10), (15, 8), (25, 12)):
        for slatr in (1.8, 2.0, 2.2):
            for risk in (0.01, 0.0125, 0.015):
                for rr in (1.5, 2.0, 2.5):
                    for ema in (True, False):
                        for cap in (0.0, 2.2):
                            jobs.append(
                                (
                                    d1,
                                    d1a,
                                    d1e,
                                    dict(
                                        name=f"D1_e{en}x{ex}_sl{slatr}_r{risk*100:.2f}_rr{rr}_ema{int(ema)}_cap{cap}",
                                        en=en,
                                        ex=ex,
                                        slatr=slatr,
                                        risk=risk,
                                        rr=rr,
                                        ema=ema,
                                        cap=cap,
                                        both=False,
                                        partial=True,
                                        lock=True,
                                        hold_days=15,
                                        bpd=1,
                                        pause_n=2,
                                        pause_d=8,
                                        max_day=1,
                                        spread=0.40,
                                    ),
                                )
                            )
    # H1 long only
    for en, ex in ((24, 12), (36, 18), (48, 24)):
        for slatr in (1.8, 2.2):
            for risk in (0.005, 0.01):
                for rr in (1.5, 2.0):
                    jobs.append(
                        (
                            h1,
                            h1a,
                            h1e,
                            dict(
                                name=f"H1L_e{en}x{ex}_sl{slatr}_r{risk*100:.1f}_rr{rr}",
                                en=en,
                                ex=ex,
                                slatr=slatr,
                                risk=risk,
                                rr=rr,
                                ema=True,
                                cap=2.2,
                                both=False,
                                partial=True,
                                lock=True,
                                hold_days=5,
                                bpd=24,
                                pause_n=2,
                                pause_d=3,
                                max_day=1,
                                spread=0.35,
                            ),
                        )
                    )
    # controls H1 both (attendu: fail)
    for en in (12, 20):
        jobs.append(
            (
                h1,
                h1a,
                h1e,
                dict(
                    name=f"H1BOTH_e{en}_ctrl",
                    en=en,
                    ex=10,
                    slatr=1.8,
                    risk=0.01,
                    rr=1.5,
                    ema=False,
                    cap=0.0,
                    both=True,
                    partial=True,
                    lock=True,
                    hold_days=2,
                    bpd=24,
                    pause_n=2,
                    pause_d=1,
                    max_day=2,
                    spread=0.35,
                ),
            )
        )

    print(f"jobs={len(jobs)}")
    results = []
    for i, (rows, atrs, emas, cfg) in enumerate(jobs, 1):
        results.append(sim(rows, atrs, emas, cfg))
        if i % 40 == 0:
            print(f"  {i}/{len(jobs)}")

    results.sort(key=lambda r: (r["ok"], r["loss_ok"], r["net"]), reverse=True)
    ok = [r for r in results if r["ok"]]

    lines = [
        "MEILLEUR FTMO 2020+ — MT5 XAUUSD, OHLC pessimiste (SL gagne si conflit)",
        "Regles: -5% jour / -10% total sur capital INITIAL 100k | 1 position",
        "",
        "PHOTO +13M / WR93% / 10k depot:",
        "  Rejetee comme cible. Hors FTMO (compounding + perte moy >> gain moy).",
        "",
        f"Configs testees: {len(results)} | OK+profit: {len(ok)}",
        "",
        "=== TOP 12 ===",
    ]
    for r in results[:12]:
        lines.append(
            f"{r['name']}: net {r['net']:+.0f}$ | ~/m {r['month']:+.0f}$ | "
            f"n={r['trades']} WR{r['wr']:.0f}% B{r['buys']}/S{r['sells']} | "
            f"DD {r['dd']:.1f}% | 1/{r['gap']:.1f}j | "
            f"{'OK' if r['loss_ok'] else 'FAIL'}{' HALT' if r['halt'] else ''} | "
            f"+10% {r['t10'].date() if r['t10'] else '-'}"
        )

    lines.append("")
    if ok:
        best = max(ok, key=lambda r: r["net"])
        fast = [r for r in ok if r["t10"]]
        fast.sort(key=lambda r: (r["t10"], -r["net"]))
        lines.append(f"RETENU: {best['name']}")
        lines.append(
            f"  Net {best['net']:+.0f}$ | ~/mois {best['month']:+.0f}$ | "
            f"WR {best['wr']:.0f}% | DD {best['dd']:.1f}% | "
            f"{best['trades']} trades | 1/{best['gap']:.1f}j"
        )
        lines.append(
            f"  Challenge: +5% {best['t5'].date() if best['t5'] else '-'} | "
            f"+10% {best['t10'].date() if best['t10'] else '-'}"
        )
        if fast:
            f = fast[0]
            lines.append(
                f"PLUS RAPIDE +10%: {f['name']} le {f['t10'].date()} "
                f"(net {f['net']:+.0f}$ DD {f['dd']:.1f}%)"
            )
        # recommend for EA
        lines.append("")
        lines.append("PARAMS EA GoldFTMO.mq5 a utiliser:")
        lines.append(f"  -> {best['name']}")
    else:
        lines.append("Aucun OK+profit.")

    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
