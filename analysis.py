"""Load the merged Excel dataset and recompute every analysis behind the charts.

The only input is data/Bangladesh_Crime_Statistics_Jan2019-Aug2026.xlsx:
  * "Merged Data": 92 months x 17 police units (no national Total rows);
    national figures are the sum of the 17 units.
  * "Notes": the translated PHQ footnotes, parsed for the number of delayed
    ("backlog") murder filings in each month.
  * "Sources": the PDF behind each month.

Methods are the same as in the report (src/06_analysis.py, src/07_ml.py).
"""
from pathlib import Path
import hashlib
import itertools
import pickle
import re
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
XLSX = HERE / "data" / "Bangladesh_Crime_Statistics_Jan2019-Aug2026.xlsx"
CACHE = HERE / ".cache"

CRIME = ["Dacoity", "Robbery", "Murder", "Speedy Trial", "Riot",
         "Woman & Child Repression", "Kidnapping", "Police Assault",
         "Burglary", "Theft", "Other Cases"]
RECOVERY = ["Arms Act", "Explosive Act", "Narcotics", "Smuggling"]
HEADS = CRIME + RECOVERY
REPORTED = "Reported Crime (excl. Recovery)"
MURDER_ADJ = "Murder (excl. backlog filings)"
SERIES = HEADS + [MURDER_ADJ, "Recovery Total", REPORTED, "Total Cases"]
VIOLENT = ["Murder", "Dacoity", "Robbery", "Kidnapping"]

UNITS = ["DMP", "CMP", "KMP", "RMP", "BMP", "SMP", "RPMP", "GMP",
         "Dhaka Range", "Mymensingh Range", "Chittagong Range", "Sylhet Range",
         "Khulna Range", "Barishal Range", "Rajshahi Range", "Rangpur Range",
         "Railway Range"]
UNIT_FULL = {"DMP": "Dhaka Metropolitan Police", "CMP": "Chattogram Metropolitan Police",
             "KMP": "Khulna Metropolitan Police", "RMP": "Rajshahi Metropolitan Police",
             "BMP": "Barishal Metropolitan Police", "SMP": "Sylhet Metropolitan Police",
             "RPMP": "Rangpur Metropolitan Police", "GMP": "Gazipur Metropolitan Police"}
# Census division each unit polices (metro units sit inside their division).
DIVISION = {"DMP": "Dhaka", "GMP": "Dhaka", "Dhaka Range": "Dhaka",
            "CMP": "Chattogram", "Chittagong Range": "Chattogram",
            "KMP": "Khulna", "Khulna Range": "Khulna",
            "RMP": "Rajshahi", "Rajshahi Range": "Rajshahi",
            "BMP": "Barishal", "Barishal Range": "Barishal",
            "SMP": "Sylhet", "Sylhet Range": "Sylhet",
            "RPMP": "Rangpur", "Rangpur Range": "Rangpur",
            "Mymensingh Range": "Mymensingh"}
# BBS Population & Housing Census 2022, adjusted (The Business Standard, 9 Apr 2023).
POP = {"Dhaka": 45_643_915, "Chattogram": 34_178_581, "Rajshahi": 20_794_023,
       "Rangpur": 18_020_073, "Khulna": 17_813_957, "Mymensingh": 12_637_524,
       "Sylhet": 11_415_021, "Barishal": 9_325_818}

BREAK = pd.Timestamp("2024-08-31")          # the month of 5 August 2024
PRE = (pd.Timestamp("2022-08-31"), pd.Timestamp("2024-07-31"))
POST = (pd.Timestamp("2024-09-30"), pd.Timestamp("2026-08-31"))
COVID = (pd.Timestamp("2020-03-26"), pd.Timestamp("2020-05-30"))


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load():
    x = pd.ExcelFile(XLSX)
    m = pd.read_excel(x, "Merged Data")
    m = m.rename(columns={"Month Tag": "date", "Police Unit": "unit",
                          "Unit Type": "unit_type", "Year": "year", "Month": "month"})
    m = m.rename(columns={f"Recovery Cases - {h}": h for h in RECOVERY})
    m["date"] = pd.to_datetime(m["date"])

    # the two printed identities hold in every row
    assert (m[RECOVERY].sum(axis=1) == m["Recovery Total"]).all()
    assert (m[CRIME].sum(axis=1) + m["Recovery Total"] == m["Total Cases"]).all()
    assert len(m) == m.date.nunique() * len(UNITS)

    m[REPORTED] = m["Total Cases"] - m["Recovery Total"]
    m["division"] = m.unit.map(DIVISION).fillna("-")
    num = HEADS + ["Recovery Total", "Total Cases", REPORTED]
    nat = m.groupby("date")[num].sum().sort_index()

    notes = pd.read_excel(x, "Notes", header=None)[0].dropna().astype(str)
    backlog, note_text = {}, {}
    for line in notes:
        g = re.match(r"^(\d{2} \w{3} \d{4}): (.*)$", line)
        if not g or "murder" not in g.group(2).lower():
            continue
        d = pd.to_datetime(g.group(1), format="%d %b %Y")
        tail = g.group(2).split("include", 1)[1]
        backlog[d] = sum(int(n) for n in re.findall(r"(\d+) (?:earlier-unfiled )?cases", tail))
        note_text[d] = g.group(2)
    nat["backlog_murder_cases"] = pd.Series(backlog).reindex(nat.index).fillna(0).astype(int)
    nat[MURDER_ADJ] = nat["Murder"] - nat["backlog_murder_cases"]
    nat["backlog_note"] = pd.Series(note_text).reindex(nat.index).fillna("")
    nat["year"] = nat.index.year

    src = pd.read_excel(x, "Sources", header=3)
    src = src[pd.to_datetime(src["Month Tag"], errors="coerce").notna()].copy()
    src["Month Tag"] = pd.to_datetime(src["Month Tag"])
    return m, nat, src


def data_hash():
    return hashlib.sha1(XLSX.read_bytes()).hexdigest()[:12]


def cached(name, fn):
    """Cache slow model fits on the hash of the Excel file."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{name}_{data_hash()}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    out = fn()
    f.write_bytes(pickle.dumps(out))
    return out


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def cliffs_delta(a, b):
    gt = (b[:, None] > a[None, :]).sum()
    lt = (b[:, None] < a[None, :]).sum()
    return (gt - lt) / (len(a) * len(b))


def boot_ratio(a, b, n=5000, seed=7):
    rng = np.random.default_rng(seed)
    ra = rng.choice(a, (n, len(a))).mean(1)
    rb = rng.choice(b, (n, len(b))).mean(1)
    return np.percentile(rb / ra, [2.5, 97.5])


def pre_post(nat):
    from scipy import stats
    pre, post = nat.loc[PRE[0]:PRE[1]], nat.loc[POST[0]:POST[1]]
    rows = []
    for s in SERIES:
        a, b = pre[s].to_numpy(float), post[s].to_numpy(float)
        lo, hi = boot_ratio(a, b)
        rows.append(dict(series=s, pre_mean=a.mean(), post_mean=b.mean(),
                         pct_change=100 * (b.mean() / a.mean() - 1),
                         ratio_lo=lo, ratio_hi=hi,
                         p_value=stats.mannwhitneyu(a, b, alternative="two-sided").pvalue,
                         cliffs_delta=cliffs_delta(a, b)))
    return pd.DataFrame(rows).set_index("series")


def its(nat):
    """Segmented negative-binomial regression per series, with counterfactual."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    d = nat.reset_index()[["date"] + SERIES].copy()
    d["t"] = np.arange(len(d))
    d["month"] = d.date.dt.month.astype(str)
    d["post"] = (d.date > BREAK).astype(int)
    d["aug24"] = (d.date == BREAK).astype(int)
    t0 = d.loc[d.date == BREAK, "t"].iloc[0]
    d["t_post"] = np.where(d.post == 1, d.t - t0, 0)
    d["covid"] = d.date.between("2020-03-31", "2020-05-31").astype(int)
    rows, fit = [], pd.DataFrame({"date": d.date})
    f = "y ~ t + post + t_post + aug24 + covid + C(month)"
    for s in SERIES:
        dd = d.rename(columns={s: "y"})
        dd["y"] = dd["y"].clip(lower=0)
        mu = smf.glm(f, dd, family=sm.families.Poisson()).fit().mu
        aux = ((dd.y - mu) ** 2 - dd.y) / mu
        alpha = max(float(sm.OLS(aux, mu).fit().params.iloc[0]), 1e-4)
        m = smf.glm(f, dd, family=sm.families.NegativeBinomial(alpha=alpha)).fit()
        ci = m.conf_int()
        rows.append(dict(series=s, irr_post=np.exp(m.params["post"]),
                         irr_post_lo=np.exp(ci.loc["post", 0]),
                         irr_post_hi=np.exp(ci.loc["post", 1]),
                         p_post=m.pvalues["post"],
                         slope_change_pct_per_yr=100 * (np.exp(12 * m.params["t_post"]) - 1)))
        cf = dd.copy()
        cf[["post", "t_post", "aug24"]] = 0
        fit[f"fit::{s}"] = m.predict(dd).to_numpy()
        fit[f"cf::{s}"] = m.predict(cf).to_numpy()
    return pd.DataFrame(rows).set_index("series"), fit.set_index("date")


def stl_all(nat):
    from statsmodels.tsa.seasonal import STL
    out, strength = {}, {}
    for s in SERIES:
        y = nat[s].astype(float)
        r = STL(np.log1p(y), period=12, robust=True).fit()
        out[s] = pd.DataFrame({"observed": y, "trend": np.expm1(r.trend),
                               "seasonal_pct": (np.exp(r.seasonal) - 1) * 100,
                               "resid_pct": (np.exp(r.resid) - 1) * 100}, index=nat.index)
        fs = max(0.0, 1 - np.var(r.resid) / np.var(r.seasonal + r.resid))
        prof = pd.Series(r.seasonal, index=nat.index).groupby(nat.index.month).mean()
        strength[s] = dict(seasonal_strength=fs, peak_month=int(prof.idxmax()),
                           trough_month=int(prof.idxmin()),
                           amplitude_pct=100 * (np.exp(prof.max() - prof.min()) - 1))
    return out, pd.DataFrame(strength).T


def division_rates(m, nat):
    months = nat.groupby("year").size()
    w = m[m.division != "-"]
    cols = HEADS + ["Recovery Total", "Total Cases", REPORTED]
    div = w.groupby(["year", "division"])[cols].sum().reset_index()
    div["months"] = div.year.map(months)
    div["population"] = div.division.map(POP)
    for s in cols:
        div[f"rate::{s}"] = div[s] / div.population * 1e5 * 12 / div.months
    return div


def window_means(df, cols, by):
    pre = df[(df.date >= PRE[0]) & (df.date <= PRE[1])].groupby(by)[cols].sum() / 24
    post = df[(df.date >= POST[0]) & (df.date <= POST[1])].groupby(by)[cols].sum() / 24
    return pre, post


# ---------------------------------------------------------------------------
# machine learning
# ---------------------------------------------------------------------------
FORECAST = ["Total Cases", REPORTED, "Murder", "Robbery", "Dacoity",
            "Woman & Child Repression", "Narcotics"]


def _exog(index):
    mth = index.month.to_numpy()
    cols = {"post": (index > BREAK).astype(float), "aug24": (index == BREAK).astype(float)}
    for k in (1, 2):
        cols[f"sin{k}"] = np.sin(2 * np.pi * k * mth / 12)
        cols[f"cos{k}"] = np.cos(2 * np.pi * k * mth / 12)
    return pd.DataFrame(cols, index=index)


def _fit(y, order, sorder, trend):
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    return SARIMAX(np.log1p(y), exog=_exog(y.index), order=order, seasonal_order=sorder,
                   trend=trend, enforce_stationarity=False,
                   enforce_invertibility=False).fit(disp=False)


def forecast(nat, h=12):
    """AIC-best d=0 and d=1 SARIMAX, kept by walk-forward backtest MAPE."""
    def run():
        perf, rows = [], []
        fut = pd.date_range(nat.index[-1] + pd.offsets.MonthEnd(1), periods=h, freq="ME")
        for s in FORECAST:
            y = nat[s].astype(float)
            y.index = pd.DatetimeIndex(y.index, freq="ME")
            actual = y.iloc[-h:].to_numpy()
            cands = []
            for d in (0, 1):
                trend = "c" if d == 0 else "n"
                best = None
                for p, q, P, Q in itertools.product([0, 1, 2], [0, 1], [0, 1], [0, 1]):
                    try:
                        mm = _fit(y, (p, d, q), (P, 0, Q, 12), trend)
                    except Exception:
                        continue
                    if best is None or mm.aic < best[0]:
                        best = (mm.aic, (p, d, q), (P, 0, Q, 12))
                order, sorder = best[1], best[2]
                preds, naive = [], []
                for k in range(h, 0, -1):
                    train = y.iloc[:-k]
                    mm = _fit(train, order, sorder, trend)
                    nxt = y.index[len(y) - k:len(y) - k + 1]
                    preds.append(np.expm1(mm.forecast(1, exog=_exog(nxt)).iloc[0]))
                    naive.append(train.iloc[-12])
                preds, naive = np.array(preds), np.array(naive)
                cands.append((np.mean(np.abs(preds - actual) / actual) * 100,
                              order, sorder, trend, preds, naive))
            mape, order, sorder, trend, preds, naive = min(cands, key=lambda c: c[0])
            mm = _fit(y, order, sorder, trend)
            f = mm.get_forecast(h, exog=_exog(fut))
            mean = np.expm1(f.predicted_mean).to_numpy()
            c95 = np.expm1(f.conf_int(alpha=0.05)).to_numpy()
            c80 = np.expm1(f.conf_int(alpha=0.20)).to_numpy()
            rows.append(pd.DataFrame({"series": s, "date": fut, "mean": mean,
                                      "lo95": c95[:, 0], "hi95": c95[:, 1],
                                      "lo80": c80[:, 0], "hi80": c80[:, 1]}))
            rows.append(pd.DataFrame({"series": s, "date": y.index[-h:], "backtest": preds,
                                      "naive": naive, "actual": actual}))
            perf.append(dict(series=s, order=order, seasonal=sorder, mape=mape,
                             mape_naive=np.mean(np.abs(naive - actual) / actual) * 100,
                             next12=mean.sum(), last12=y.iloc[-12:].sum()))
            print(f"  forecast {s}: ARIMA{order}{sorder} MAPE {mape:.1f}%")
        return pd.concat(rows, ignore_index=True), pd.DataFrame(perf).set_index("series")
    return cached("forecast", run)


CP_SERIES = ["Total Cases", REPORTED, "Narcotics", "Murder", "Robbery", "Dacoity",
             "Woman & Child Repression", "Kidnapping", "Theft", "Arms Act"]


def change_points(nat):
    import ruptures as rpt
    rows = []
    for s in CP_SERIES:
        y = nat[s].astype(float).to_numpy()
        z = (y - y.mean()) / y.std()
        bks = rpt.Pelt(model="rbf", min_size=3, jump=1).fit(z.reshape(-1, 1)).predict(pen=4)
        rows += [dict(series=s, date=nat.index[b]) for b in bks[:-1]]
    return pd.DataFrame(rows)


def anomalies(nat):
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    Xz = StandardScaler().fit_transform(np.log1p(nat[HEADS].astype(float)))
    iso = IsolationForest(n_estimators=500, contamination=0.06, random_state=42).fit(Xz)
    out = pd.DataFrame({"date": nat.index, "score": -iso.score_samples(Xz),
                        "flag": iso.predict(Xz) == -1})
    out["drivers"] = [", ".join(f"{HEADS[j]} {Xz[i, j]:+.1f} sd"
                                for j in np.argsort(-np.abs(Xz[i]))[:3])
                      for i in range(len(Xz))]
    return out


def clusters(m):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    u = m[m.unit != "Railway Range"].groupby("unit")[HEADS].sum()
    share = u.div(u.sum(axis=1), axis=0)
    logs = np.log((u + 0.5).div((u + 0.5).sum(axis=1), axis=0))
    clr = logs.sub(logs.mean(axis=1), axis=0)
    Xz = (clr - clr.mean()).to_numpy()
    km = KMeans(3, n_init=50, random_state=42).fit(Xz)
    pca = PCA(2).fit(Xz)
    pcs = pca.transform(Xz)
    res = share.copy()
    res["cluster"], res["pc1"], res["pc2"] = km.labels_, pcs[:, 0], pcs[:, 1]
    names = {}
    for k in res.cluster.unique():
        mem = set(res.index[res.cluster == k])
        names[k] = ("Metro & port belt" if "DMP" in mem else
                    "Northern agrarian ranges" if "Rangpur Range" in mem else
                    "Dhaka–Barishal ring")
    res["cluster_name"] = res.cluster.map(names)
    load = pd.DataFrame(pca.components_.T, index=HEADS, columns=["pc1", "pc2"])
    return res, load, dict(explained=pca.explained_variance_ratio_.tolist(),
                           silhouette=float(silhouette_score(Xz, km.labels_)))


# ---------------------------------------------------------------------------
def build():
    m, nat, src = load()
    print(f"loaded {len(m)} rows, {nat.index.size} months, "
          f"{int(nat['Total Cases'].sum()):,} cases, "
          f"{int(nat.backlog_murder_cases.sum())} backlog murder filings")
    pp = pre_post(nat)
    itsr, itsfit = cached("its", lambda: its(nat))
    stl, stl_strength = cached("stl", lambda: stl_all(nat))
    fc, perf = forecast(nat)
    cl, load_, meta = clusters(m)
    return dict(m=m, nat=nat, src=src, pp=pp, its=itsr, itsfit=itsfit, stl=stl,
                stl_strength=stl_strength, div=division_rates(m, nat), fc=fc, perf=perf,
                cp=change_points(nat), an=anomalies(nat), cl=cl, load=load_, meta=meta)
