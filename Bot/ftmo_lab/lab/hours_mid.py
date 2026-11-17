import numpy as np, pandas as pd, sys
for s in sys.argv[1:]:
    b = pd.read_csv(f"/data/{s}_h1.csv"); a = pd.read_csv(f"/data/{s}_h1_ask.csv")
    df = b.merge(a, on="timestamp", suffixes=("b", "a"))
    df = df[(df.volumeb > 0)]
    t = pd.to_datetime(df.timestamp, unit="ms", utc=True)
    mo = (df.openb + df.opena) / 2; mc = (df.closeb + df.closea) / 2
    out = pd.DataFrame({"y": t.dt.year, "h": t.dt.hour, "mid": (mc - mo) / mo * 1e4,
                        "bid": (df.closeb - df.openb) / df.openb * 1e4,
                        "spr_open": (df.opena - df.openb) / mo * 1e4, "spr_close": (df.closea - df.closeb) / mo * 1e4})
    out = out[out.y >= 2020]
    g = out.groupby("h")
    res = pd.DataFrame({"mid": g.mid.mean(), "bid": g.bid.mean(), "t_mid": g.mid.mean() / g.mid.std() * np.sqrt(g.size()),
                        "spr_open_med": g.spr_open.median(), "spr_close_med": g.spr_close.median()}).round(2)
    py = out.pivot_table(index="h", columns="y", values="mid", aggfunc="mean").round(1)
    print("\n==", s); print(pd.concat([res, py], axis=1).to_string())
