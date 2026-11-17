# -*- coding: utf-8 -*-
"""Chargement H1 Dukascopy + barres D1 'broker' (jour = 17h New York, comme FTMO/MT5 GMT+2/+3)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

DATA = "/data"

# Couts aller-retour en unites de prix (spread FTMO typique + commission + marge de securite)
COST = {
    "xauusd": 0.35, "xagusd": 0.035,
    "usa500idxusd": 0.6, "usatechidxusd": 2.0, "usa30idxusd": 3.0,
    "deuidxeur": 2.0, "gbridxgbp": 1.5, "jpnidxjpy": 12.0,
    "eurusd": 0.00012, "gbpusd": 0.00016, "audusd": 0.00014, "nzdusd": 0.00018,
    "btcusd": 60.0, "ethusd": 4.0, "lightcmdusd": 0.05, "brentcmdusd": 0.05,
    "fraidxeur": 2.0, "eusidxeur": 2.0, "ausidxaud": 2.0, "hkgidxhkd": 10.0, "espidxeur": 8.0,
    "usdcad": 0.00018, "usdchf": 0.00018, "usdjpy": 0.014, "eurjpy": 0.02, "gbpjpy": 0.028,
}
# Si donnees ask dispo : seulement commission/glissement en plus du spread reel
EXTRA = {"btcusd": 15.0, "ethusd": 1.0, "lightcmdusd": 0.01, "brentcmdusd": 0.01, "hkgidxhkd": 2.0,
         "xauusd": 0.10, "usa500idxusd": 0.1, "usatechidxusd": 0.4, "usa30idxusd": 0.6, "deuidxeur": 0.4}
# Nom FTMO MT5
FTMO_NAME = {
    "xauusd": "XAUUSD", "xagusd": "XAGUSD", "usa500idxusd": "US500.cash", "usatechidxusd": "US100.cash",
    "usa30idxusd": "US30.cash", "deuidxeur": "GER40.cash", "gbridxgbp": "UK100.cash", "jpnidxjpy": "JP225.cash",
}
SWAP_YEAR = 0.05  # financement 5 %/an du notionnel par nuit tenue (prudent)
SWAP = {"btcusd": 0.20, "ethusd": 0.20}  # crypto FTMO : swaps eleves
CRYPTO = {"btcusd", "ethusd"}


@dataclass
class Inst:
    name: str
    t: np.ndarray        # int64 secondes UTC (debut barre)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    bday: np.ndarray     # index jour broker de chaque barre H1
    dt: pd.DatetimeIndex  # jours broker
    do: np.ndarray
    dh: np.ndarray
    dl: np.ndarray
    dc: np.ndarray
    d_first: np.ndarray  # premiere barre H1 du jour
    d_last: np.ndarray   # derniere barre H1 du jour
    cost: float
    swap: float = 0.05
    ah: np.ndarray = None  # ask (si dispo) sinon bid + spread fixe
    al: np.ndarray = None
    ao: np.ndarray = None
    ac: np.ndarray = None
    hour: np.ndarray = None  # heure depuis debut jour broker (0..23)


@lru_cache(maxsize=None)
def load(name: str) -> Inst:
    df = pd.read_csv(f"{DATA}/{name}_h1.csv")
    df = df[(df["volume"] > 0) & (df["high"] > df["low"])].reset_index(drop=True)
    import os
    if name not in COST:
        COST[name] = float(df["close"].median()) * 0.0008
    has_ask = os.path.exists(f"{DATA}/{name}_h1_ask.csv")
    if has_ask:
        a = pd.read_csv(f"{DATA}/{name}_h1_ask.csv")[["timestamp", "open", "high", "low", "close"]]
        a.columns = ["timestamp", "ao", "ah", "al", "ac"]
        df = df.merge(a, on="timestamp", how="left")
        for k, b in (("ao", "open"), ("ah", "high"), ("al", "low"), ("ac", "close")):
            df[k] = df[k].fillna(df[b] + COST[name])
            df[k] = np.maximum(df[k], df[b])
    else:
        for k, b in (("ao", "open"), ("ah", "high"), ("al", "low"), ("ac", "close")):
            df[k] = df[b] + COST[name]
    ts = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    # jour broker : heure NY + 7h -> minuit = 17h NY
    broker = ts.dt.tz_convert("America/New_York") + pd.Timedelta(hours=7)
    bdate = broker.dt.tz_localize(None).dt.normalize()
    # pas de jour samedi/dimanche (petites barres de reprise rattachees au lundi)
    wd = bdate.dt.weekday
    if name in CRYPTO:
        wd = wd * 0
    bdate = bdate + pd.to_timedelta(np.where(wd == 5, 2, np.where(wd == 6, 1, 0)), unit="D")
    codes, uniq = pd.factorize(bdate, sort=True)
    g = df.groupby(codes)
    d = pd.DataFrame({
        "o": g["open"].first(), "h": g["high"].max(), "l": g["low"].min(), "c": g["close"].last(),
        "first": g.apply(lambda x: x.index[0]), "last": g.apply(lambda x: x.index[-1]),
        "n": g.size(),
    })
    return Inst(
        name=name,
        t=(ts.astype("int64") // 10**9).to_numpy(),
        o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
        l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
        bday=codes.astype(np.int64), dt=pd.DatetimeIndex(uniq),
        do=d["o"].to_numpy(float), dh=d["h"].to_numpy(float), dl=d["l"].to_numpy(float),
        dc=d["c"].to_numpy(float), d_first=d["first"].to_numpy(np.int64),
        d_last=d["last"].to_numpy(np.int64),
        cost=EXTRA.get(name, 0.0) if has_ask else COST[name],
        ao=df["ao"].to_numpy(float), ah=df["ah"].to_numpy(float), al=df["al"].to_numpy(float),
        ac=df["ac"].to_numpy(float), swap=SWAP.get(name, SWAP_YEAR),
        hour=((broker - broker.dt.normalize()).dt.total_seconds() // 3600).astype(int).to_numpy(),
    )


# ---------------- indicateurs (style MT5) ----------------
def atr(h, l, c, n):
    tr = np.empty_like(c)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.full_like(c, np.nan)
    if len(c) <= n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(c)):  # MT5 iATR = SMA du TR ; Wilder proche, on garde SMA
        out[i] = out[i - 1] + (tr[i] - tr[i - n]) / n
    return out


def sma(x, n):
    s = pd.Series(x).rolling(n).mean().to_numpy()
    return s


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.maximum(d, 0)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50).to_numpy()


def hhv(x, n):
    return pd.Series(x).rolling(n).max().to_numpy()


def llv(x, n):
    return pd.Series(x).rolling(n).min().to_numpy()
