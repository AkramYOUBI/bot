# Poids max-Sharpe (long-only, regularises) sur 2020-2022, test 2023-2026
import numpy as np, pandas as pd
df = pd.read_pickle("/out/comp_daily.pkl")
cand = ["gold:lightcmdusd", "gold:brentcmdusd", "gold:btcusd", "gold:ethusd", "cryL:btcusd", "cryL:ethusd", "cry55:btcusd", "gold:xauusd", "goldboth:xauusd", "dbl7:xauusd", "gold:xagusd",
        "ibs:usatechidxusd", "ibs:usa500idxusd", "ibs:usa30idxusd", "ibs:deuidxeur",
        "ibsx08:usatechidxusd", "rsi2:usa500idxusd", "rsi2t20:usatechidxusd", "rsi2t20:usa500idxusd",
        "dbl7:usa30idxusd", "down3:deuidxeur", "down3:usa500idxusd", "rsi2:usa30idxusd", "ibs:gbridxgbp"]
X = df[cand]
def sharpe(r): return r.mean() / r.std() * np.sqrt(252)
def maxsharpe(R, shrink=0.5, iters=4000):
    mu = R.mean().values; cov = R.cov().values
    d = np.diag(np.diag(cov)); cov = (1 - shrink) * cov + shrink * d
    mu = 0.5 * mu + 0.5 * mu.mean()  # shrink des moyennes
    w = np.ones(len(mu)) / len(mu)
    for _ in range(iters):  # gradient projete simple
        p = w @ mu; v = w @ cov @ w
        g = mu / np.sqrt(v) - p * (cov @ w) / v ** 1.5
        w = np.maximum(w + 0.01 * g / np.abs(g).max(), 0); w /= w.sum()
    return w
tr, te = X[:"2022-12-31"], X["2023-01-01":]
for name, w in [("egal", np.ones(len(cand)) / len(cand)), ("maxS_train", maxsharpe(tr)), ("maxS_full", maxsharpe(X))]:
    p = X @ w
    print(f"{name:12s} Sharpe full {sharpe(p):.2f} | train {sharpe(tr @ w):.2f} | test {sharpe(te @ w):.2f}")
    print("   ", " ".join(f"{c}={x:.2f}" for c, x in zip(cand, w / w.max()) if x > 0.01))
# structure simple : groupes
groups = {"oil": ["gold:lightcmdusd"], "cry": ["cryL:btcusd", "cryL:ethusd"], "gold": ["gold:xauusd"], "dbl7g": ["dbl7:xauusd"], "ibs": ["ibs:usatechidxusd", "ibs:usa500idxusd", "ibs:usa30idxusd", "ibs:deuidxeur"],
          "rsi2": ["rsi2:usa500idxusd", "rsi2t20:usatechidxusd"], "dbl7i": ["dbl7:usa30idxusd"]}
for wts in [dict(gold=1, oil=0.7, cry=0.5, dbl7g=0.5, ibs=0.4, rsi2=0.6, dbl7i=0.4), dict(gold=1, oil=1, cry=0.7, dbl7g=0.6, ibs=0.4, rsi2=0.6, dbl7i=0.4),
            dict(gold=1, oil=0.7, cry=0.3, dbl7g=0.5, ibs=0.4, rsi2=0.6, dbl7i=0.4), dict(gold=1, dbl7g=0.5, ibs=0.5, rsi2=0.5, dbl7i=0.5), dict(gold=1, dbl7g=0.5, ibs=0.4, rsi2=0.6, dbl7i=0.4),
            dict(gold=1, dbl7g=0.6, ibs=0.35, rsi2=0.5, dbl7i=0.35), dict(gold=1, dbl7g=0, ibs=0.5, rsi2=0.5, dbl7i=0)]:
    p = sum(X[c] * v for k, v in wts.items() for c in groups[k])
    yrs = p.groupby(p.index.year).apply(sharpe).round(1).to_dict()
    print(f"groupes {wts}: Sharpe {sharpe(p):.2f} train {sharpe(p[:'2022'] ):.2f} test {sharpe(p['2023':]):.2f} | par an {yrs}")
