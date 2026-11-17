import strategies as S
from data import load
from adaptive_dev import st, DEV
S.DELAY["h"] = 2
I = load("xaulong")
def tag(tr):  # ajoute regime factice pour st()
    return [(t[0], t[1], t[2], 0) for t in tr]
for name, tr in {
    "mom regime 2 sens": S.regime_mom(I), "mom regime achat": S.regime_mom(I, sides=(1,)),
    "mom regime vente": S.regime_mom(I, sides=(-1,)), "mom look120 2 sens": S.regime_mom(I, look=120),
    "d7 regime 2 sens": S.regime_d7(I), "d7 regime achat": S.regime_d7(I, sides=(1,)), "d7 regime vente": S.regime_d7(I, sides=(-1,)),
}.items():
    print(f"{name:22s} {st(tag(tr), *DEV)}")
