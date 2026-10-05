"""Build the interactive website into docs/ (served by GitHub Pages).

    python build_site.py

Reads only data/Bangladesh_Crime_Statistics_Jan2019-Aug2026.xlsx (plus the
division boundaries in data/bgd_adm1.geojson), recomputes the analysis,
writes every chart as a Plotly / Vega-Lite JSON spec in a light and a dark
variant, and renders index.html: a single page with the dashboard
(Figure 1) followed by the story. All numbers in the text are computed here, none typed by hand.
"""
from datetime import date
from html import escape
import json
import math
import shutil

import numpy as np
import pandas as pd
import plotly.io as pio

import analysis as A
import charts as C
from theme import THEMES, vega_config

HERE = A.HERE
DOCS = HERE / "docs"
PDFS = HERE / "data" / "raw_pdf"
REPO = "https://github.com/spaul571/bangladesh-crime-viz"


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------
def _round(o):
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return round(o, 4)
    if isinstance(o, list):
        return [_round(v) for v in o]
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    return o


def spec_of(ch, T):
    if ch.kind == "plotly":
        spec = json.loads(pio.to_json(ch.obj, validate=False))
        spec["layout"]["height"] = ch.height
        spec["layout"].pop("template", None)
    else:
        spec = ch.obj.to_dict()
        spec["config"] = vega_config(T)
        spec["autosize"] = {"type": "fit-x", "contains": "padding"} if ch.fit == "single" else {"type": "pad"}
    return _round({"kind": ch.kind, "spec": spec, "controls": ch.controls, "fit": ch.fit})


def write_charts(R):
    for T in THEMES:
        (DOCS / "charts" / T.name).mkdir(parents=True, exist_ok=True)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    sizes = {}
    for cid, fn in C.BUILDERS.items():
        for T in THEMES:
            ch = fn(T, R)
            out = DOCS / "charts" / T.name / f"{cid}.json"
            out.write_text(json.dumps(spec_of(ch, T), separators=(",", ":"), ensure_ascii=False),
                           encoding="utf-8")
            if T.name == "light":
                HEIGHT[cid] = ch.height
                sizes[cid] = out.stat().st_size // 1024
                if ch.data is not None:
                    d = ch.data.copy()
                    for c in d.columns:
                        if pd.api.types.is_float_dtype(d[c]):
                            d[c] = d[c].round(4)
                    d.to_csv(DOCS / "data" / f"{cid}.csv", index=False)
    print("chart specs (KB):", sizes)


def write_explorer_data(R):
    m = R["m"]
    cols = A.HEADS + ["Recovery Total", "Total Cases", A.REPORTED]
    months = sorted(m.date.unique())
    vals = []
    for d in months:
        sub = m[m.date == d].set_index("unit").loc[A.UNITS, cols]
        vals.append(sub.astype(int).values.tolist())
    out = {"months": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in months], "units": A.UNITS,
           "unit_type": [m[m.unit == u].unit_type.iloc[0] for u in A.UNITS],
           "division": [A.DIVISION.get(u) for u in A.UNITS],
           "cols": cols, "heads": A.HEADS, "family": {h: C.FAMILY[h] for h in A.HEADS},
           "pop": A.POP, "iso": C.ISO, "anchor": C.ANCHOR, "geo": _round(C.GEO),
           "backlog": [int(R["nat"].loc[d, "backlog_murder_cases"]) for d in months], "values": vals}
    (DOCS / "data" / "explorer.json").write_text(json.dumps(out, separators=(",", ":")),
                                                 encoding="utf-8")


# ---------------------------------------------------------------------------
# numbers for the text
# ---------------------------------------------------------------------------
def pct(v, nd=1, sign=True):
    s = f"{v:+.{nd}f}%" if sign else f"{v:.{nd}f}%"
    return s.replace("-", "−")


def num(v, nd=0):
    return f"{v:,.{nd}f}".replace("-", "−")


def numbers(R):
    nat, pp, its, m = R["nat"], R["pp"], R["its"], R["m"]
    tot = nat["Total Cases"]
    N = dict(months=len(nat), n_pdf=len(list(PDFS.glob("*.pdf"))), first=f"{nat.index[0]:%B %Y}", last=f"{nat.index[-1]:%B %Y}",
             grand=num(tot.sum()), reported=num(nat[A.REPORTED].sum()),
             recovery=num(nat["Recovery Total"].sum()),
             rec_share=pct(100 * nat["Recovery Total"].sum() / tot.sum(), sign=False),
             narco_share=pct(100 * nat.Narcotics.sum() / tot.sum(), sign=False),
             wcr_share=pct(100 * nat["Woman & Child Repression"].sum() / nat[A.REPORTED].sum(), sign=False),
             murder_total=num(nat.Murder.sum()),
             murder_share=pct(100 * nat.Murder.sum() / tot.sum(), sign=False),
             peak=num(tot.max()), peak_month=f"{tot.idxmax():%B %Y}",
             aug24=num(tot.loc["2024-08-31"]), jul24=num(tot.loc["2024-07-31"]),
             aug_drop=pct(100 * (1 - tot.loc["2024-08-31"] / tot.loc["2024-07-31"]), sign=False),
             apr20=num(tot.loc["2020-04-30"]),
             rec_apr20=num(nat.loc["2020-04-30", "Recovery Total"]),
             riot_jul24=num(nat.loc["2024-07-31", "Riot"]),
             pa_jul24=num(nat.loc["2024-07-31", "Police Assault"]),
             narco_jul24=num(nat.loc["2024-07-31", "Narcotics"]),
             narco_aug24=num(nat.loc["2024-08-31", "Narcotics"]),
             murder_aug24=num(nat.loc["2024-08-31", "Murder"]),
             backlog_aug24=num(nat.loc["2024-08-31", "backlog_murder_cases"]),
             backlog=num(nat.backlog_murder_cases.sum()),
             p_murder_adj=f"{pp.loc[A.MURDER_ADJ, 'p_value']:.2f}")
    for s in [x for x in A.SERIES if x != A.MURDER_ADJ]:
        k = s.split(" (")[0].replace(" ", "").replace("&", "")
        N[f"chg_{k}"] = pct(pp.loc[s, "pct_change"])
        N[f"pre_{k}"] = num(pp.loc[s, "pre_mean"])
        N[f"post_{k}"] = num(pp.loc[s, "post_mean"])
        N[f"cliff_{k}"] = f"{pp.loc[s, 'cliffs_delta']:.2f}"
        N[f"irr_{k}"] = f"{its.loc[s, 'irr_post']:.2f}"
        N[f"irrci_{k}"] = f"{its.loc[s, 'irr_post_lo']:.2f}–{its.loc[s, 'irr_post_hi']:.2f}"
    N["chg_MurderAdj"] = pct(pp.loc[A.MURDER_ADJ, "pct_change"])
    N["irr_MurderAdj"] = f"{its.loc[A.MURDER_ADJ, 'irr_post']:.2f}"
    N["irrci_MurderAdj"] = (f"{its.loc[A.MURDER_ADJ, 'irr_post_lo']:.2f}–"
                            f"{its.loc[A.MURDER_ADJ, 'irr_post_hi']:.2f}")
    st = R["stl_strength"].loc[A.REPORTED]
    N.update(seas_strength=f"{st.seasonal_strength:.2f}",
             seas_peak=f"{pd.Timestamp(2000, int(st.peak_month), 1):%B}",
             seas_trough=f"{pd.Timestamp(2000, int(st.trough_month), 1):%B}",
             seas_amp=pct(st.amplitude_pct, 0, sign=False))
    # divisions
    div = R["div"]
    r25 = div[div.year == 2025].set_index("division")[f"rate::{A.REPORTED}"].sort_values()
    N.update(rate_hi_div=r25.index[-1], rate_hi=num(r25.iloc[-1]), rate_lo_div=r25.index[0],
             rate_lo=num(r25.iloc[0]), rate_lo2_div=r25.index[1], rate_lo2=num(r25.iloc[1]))
    w = m[m.division != "-"]
    pre, post = A.window_means(w, A.VIOLENT, "division")
    vc = ((post.sum(axis=1) / pre.sum(axis=1) - 1) * 100).sort_values(ascending=False)
    N["violent_div_top"] = ", ".join(f"{pct(v, 0)} in {d}" for d, v in vc.iloc[:3].items())
    N["violent_div_low"] = ", ".join(f"{pct(v, 0)} in {d}" for d, v in vc.iloc[::-1].iloc[:2].items())
    pre_u, post_u = A.window_means(m, A.VIOLENT, "unit")
    uc = ((post_u.sum(axis=1) / pre_u.sum(axis=1) - 1) * 100).sort_values(ascending=False)
    flat = uc[uc < 2]
    N["unit_top"] = ", ".join(f"{u} ({pct(v, 0)})" for u, v in uc.iloc[:3].items())
    N["unit_flat"] = ", ".join(f"{u} ({pct(v, 0)}, essentially flat)" if abs(v) < 2 else f"{u} ({pct(v, 0)})"
                              for u, v in flat.items()) or "none"
    N["n_units_rose"] = int((uc >= 2).sum())
    N["n_flat"] = len(flat)
    # 2026 so far
    a, b = nat.loc["2025-01-31":"2025-08-31"], nat.loc["2026-01-31":"2026-08-31"]
    ytd = {}
    for nm, c in [("Total cases", "Total Cases"), ("Reported crime (excl. recovery)", A.REPORTED),
                  ("Recovery cases", "Recovery Total"), ("of which narcotics", "Narcotics"),
                  ("Murder", "Murder"), ("Dacoity", "Dacoity"), ("Robbery", "Robbery"),
                  ("Kidnapping", "Kidnapping")]:
        ytd[nm] = (a[c].sum(), b[c].sum(), 100 * (b[c].sum() / a[c].sum() - 1))
    N["ytd"] = ytd
    for k, c in [("rec", "Recovery cases"), ("narco", "of which narcotics"), ("dac", "Dacoity"),
                 ("kid", "Kidnapping"),
                 ("mur", "Murder"), ("rob", "Robbery")]:
        N[f"ytd_{k}"] = pct(ytd[c][2])
        N[f"ytdw_{k}"] = ("down " if ytd[c][2] < 0 else "up ") + pct(abs(ytd[c][2]), sign=False)
    # ML
    an = R["an"]
    fl = an[an.flag].sort_values("score", ascending=False)
    N["anom_months"] = ", ".join(f"{d:%b %Y}" for d in fl.date)
    cp = R["cp"]

    def cps(s):
        return ", ".join(f"{d:%B %Y}" for d in cp[cp.series == s].date if d >= pd.Timestamp("2024-01-01"))
    N.update(cp_dac=cps("Dacoity"), cp_kid=cps("Kidnapping"), cp_rob=cps("Robbery"))
    perf = R["perf"]
    for k, s in [("total", "Total Cases"), ("rep", A.REPORTED), ("mur", "Murder")]:
        N[f"fc_next_{k}"] = num(perf.loc[s, "next12"])
        N[f"fc_last_{k}"] = num(perf.loc[s, "last12"])
        N[f"fc_mape_{k}"] = f"{perf.loc[s, 'mape']:.1f}%"
        N[f"fc_naive_{k}"] = f"{perf.loc[s, 'mape_naive']:.1f}%"
    fut = R["fc"].dropna(subset=["mean"]).date
    N.update(fc_first=f"{fut.min():%B %Y}", fc_last=f"{fut.max():%B %Y}")
    cl, meta = R["cl"], R["meta"]
    for nm in cl.cluster_name.unique():
        N[f"cl_{nm[:5]}"] = ", ".join(sorted(cl.index[cl.cluster_name == nm]))
    N.update(pca_var=f"{100 * sum(meta['explained']):.0f}%", sil=f"{meta['silhouette']:.2f}")
    # ranks
    yr = m[m.unit != "Railway Range"].groupby(["year", "unit"])[A.REPORTED].sum().reset_index()
    top2 = yr.sort_values(A.REPORTED, ascending=False).groupby("year").head(2)
    sets = top2.groupby("year").unit.apply(frozenset)
    N["top2_same"] = " and ".join(sorted(sets.iloc[0])) if sets.nunique() == 1 else ""
    vio = nat[["Dacoity", "Robbery", "Kidnapping"]].sum(axis=1)
    med = vio.groupby(nat.year).median()
    N.update(med_lo=num(med.loc[2019:2023].min()), med_hi=num(med.loc[2019:2023].max()),
             med25=num(med.loc[2025]))
    return N


# ---------------------------------------------------------------------------
# page pieces
# ---------------------------------------------------------------------------
REPORT_FIG = {  # id -> (report figure number, library used in the report)
    "sunburst": (2, "Plotly"), "hero": (3, "matplotlib"), "calendar": (4, "seaborn"),
    "seasonal": (5, "Vega-Altair"), "stl": (6, "matplotlib"), "correlation": (7, "seaborn"),
    "small_multiples": (8, "matplotlib"), "forest": (9, "matplotlib"), "its": (10, "matplotlib"),
    "anomalies": (11, "matplotlib"), "murder_backlog": (12, "matplotlib"), "ridgeline": (13, "seaborn"),
    "family_share": (14, "Vega-Altair"), "yoy": (15, "Vega-Altair"), "map_rates": (16, "Plotly"),
    "map_change": (16, "Plotly"), "dumbbell": (17, "Plotly"), "unit_heatmap": (18, "seaborn"),
    "bump": (19, "Vega-Altair"), "clusters": (20, "matplotlib"), "radar": (21, "Plotly"),
    "brush": (22, "Vega-Altair"), "forecast": (23, "matplotlib"), "race": (None, "Plotly"),
}
VEGA = {"seasonal", "family_share", "yoy", "bump", "brush"}
MINW = {"small_multiples": 760, "correlation": 680, "forest": 620, "unit_heatmap": 720,
        "anomalies": 640, "stl": 560, "bump": 620, "seasonal": 0, "brush": 0, "radar": 560,
        "calendar": 560, "dumbbell": 560, "race": 520, "clusters": 600, "map_rates": 420,
        "map_change": 420}
HEIGHT = {}
FIGNO = {"n": 0}
FIGS = {}


def figure(cid, title, sub, hint, wide=False, source=None):
    FIGNO["n"] += 1
    n = FIGS[cid] = FIGNO["n"]
    rep, lib = REPORT_FIG[cid]
    site_lib = "Vega-Altair" if cid in VEGA else "Plotly"
    if rep is None:
        origin = f"Web-only chart, drawn with {site_lib}."
    elif lib == site_lib:
        origin = f"Report Figure {rep}, drawn with {lib}."
    else:
        origin = f"Report Figure {rep} was drawn with {lib}; redrawn here with {site_lib} so it is interactive."
    src = source or "Source: Bangladesh Police Headquarters, monthly crime statistics, Jan 2019 – Aug 2026."
    return f"""
<figure class="viz{' wide' if wide else ''}" id="fig-{cid}">
  <figcaption class="viz-head">
    <span class="fig-no">Figure {n}</span>
    <h3>{title}</h3>
    <p class="sub">{sub}</p>
  </figcaption>
  <div class="controls" data-for="{cid}"><span class="hint">{hint}</span></div>
  <div class="scroll"><div class="chart" data-id="{cid}" data-minw="{MINW.get(cid, 0)}" style="min-height:{HEIGHT.get(cid, 400)}px"
       role="img" aria-label="{escape(title)}"><div class="loading">Loading chart…</div></div></div>
  <div class="viz-foot">
    <span>{src}</span>
    <span class="lib">{origin}</span>
    <a href="data/{cid}.csv" download>Chart data (CSV)</a>
  </div>
</figure>"""


def chapter(cid, kicker, title, lede):
    return f"""
<section class="chapter" id="{cid}">
  <p class="kicker">{kicker}</p>
  <h2>{title}</h2>
  <p class="lede">{lede}</p>"""


def keybox(title, body):
    return f'<aside class="keybox"><h4>{title}</h4><p>{body}</p></aside>'


def ytd_table(N):
    rows = "".join(
        f"<tr><td>{'<span class=\"indent\">' + k + '</span>' if k.startswith('of') else k}</td>"
        f"<td>{num(a)}</td><td>{num(b)}</td>"
        f"<td class=\"{'up' if c > 0 else 'down'}\">{pct(c)}</td></tr>"
        for k, (a, b, c) in N["ytd"].items())
    return f"""
<div class="table-wrap"><table class="ytd">
  <caption>January–August 2026 against January–August 2025, national cases</caption>
  <thead><tr><th>Series</th><th>Jan–Aug 2025</th><th>Jan–Aug 2026</th><th>Change</th></tr></thead>
  <tbody>{rows}</tbody></table></div>"""


def pdf_copy(title):
    """File name of the downloaded PDF, e.g. 'Crime Statistics, Jun-2025' -> crime_stats_Jun-2025.pdf."""
    name = "crime_stats_" + title.replace("Crime Statistics", "").strip(" ,()").replace(" ", "") + ".pdf"
    return name if (PDFS / name).exists() else None


def sources_table(src):
    rows = []
    for _, r in src.iterrows():
        copy = pdf_copy(str(r.iloc[1]))
        rows.append(
            f"<tr><td>{r['Month Tag']:%d %b %Y}</td><td>{escape(str(r.iloc[1]))}</td>"
            f"<td>{int(r.iloc[2]) if pd.notna(r.iloc[2]) else ''}</td><td>{escape(str(r.iloc[3]))}</td>"
            f"<td><a href=\"{escape(str(r.iloc[4]))}\" rel=\"noopener\">police.gov.bd</a></td>"
            f"<td>{f'<a href=\"{REPO}/blob/main/data/raw_pdf/{copy}\" rel=\"noopener\">GitHub</a>' if copy else ''}</td></tr>")
    return f"""
<details class="sources"><summary>Source PDF for each of the 92 months</summary>
<div class="table-wrap"><table>
<thead><tr><th>Month tag</th><th>PDF title on police.gov.bd</th><th>Page</th><th>Uploaded</th><th>Original</th><th>Copy</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></details>"""


def head(title, desc, extra=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{escape(desc)}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{escape(desc)}">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="assets/site.css">
<script>
  (function () {{
    try {{ var t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; }} catch (e) {{}}
  }})();
</script>
<script defer src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@3.1.1/plotly.min.js"></script>
{extra}
</head>"""


def nav():
    links = [("#overview", "Overview"), ("#story", "Story"), ("#rupture", "The break"),
             ("#geography", "Geography"), ("#future", "Outlook"), ("#data", "Data")]
    items = "".join(f'<a href="{h}">{t}</a>' for h, t in links)
    return f"""
<header class="topbar">
  <a class="brand" href="#top">Bangladesh crime, 2019–2026</a>
  <nav>{items}</nav>
  <button class="theme-toggle" type="button" aria-label="Switch colour theme" title="Switch light / dark">
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z" fill="currentColor"/></svg>
  </button>
</header>"""


def footer():
    return f"""
<footer class="site-foot">
  <p>Data: Bangladesh Police Headquarters monthly crime statistics (police.gov.bd), digitised from the scanned
  PDFs and merged into one Excel file. Population: BBS Population and Housing Census 2022 (adjusted).
  Built {date.today():%d %B %Y} from <code>Bangladesh_Crime_Statistics_Jan2019-Aug2026.xlsx</code>.</p>
  <p>CSE628 Data Visualization, Fall 2026 · Class Test 1 (group task) ·
  <a href="{REPO}">Source code on GitHub</a></p>
</footer>"""


# ---------------------------------------------------------------------------
def index_html(R, N):
    nat = R["nat"]
    body = []
    body.append("<main>")
    body.append(overview_html(N))
    body.append(f"""
<section class="hero" id="story">
  <p class="kicker">The story · Bangladesh Police crime statistics, {N['first']} – {N['last']}</p>
  <p class="dek">Every monthly crime table Bangladesh Police Headquarters published from {N['first']} to
  {N['last']}, digitised and merged into one dataset: {N['grand']} cases in {N['months']} months across 17 police
  units. Recorded cases fell after 5 August 2024, yet the crimes victims report rose. The overview above lets you
  filter the whole dataset by period, police unit and crime head; the chapters below explain what changed. Every
  chart is interactive: hover for values, use the menus to switch series, drag to zoom, double-click to reset.</p>
</section>""")

    body.append(chapter("numbers", "Chapter 1 · What is counted, and how much?", "A country in numbers",
                        "Most of what the police count is not crime that someone reported. It is crime the police went looking for."))
    body.append(f"""<p>The {N['grand']} cases fall into two families of almost equal size. <em>Reported crime</em>
    ({N['reported']} cases) is led by the catch-all “other cases” and by woman and child repression, which alone is
    {N['wcr_share']} of reported crime. <em>Recovery cases</em> ({N['recovery']}, {N['rec_share']} of the total) are
    police-initiated seizures; narcotics alone are {N['narco_share']} of everything recorded. Murder, the crime that
    dominates headlines, is {N['murder_total']} cases, {N['murder_share']} of the total. Click a ring to zoom into a family.</p>""")
    body.append(figure("sunburst", "What gets counted", "Inner ring: crime family; outer ring: crime head. Share of all cases, Jan 2019 – Aug 2026.",
                       "Click a family to zoom in; click the centre to zoom out."))
    body.append(f"""<p>Because the two families move in opposite directions, the national total misleads on its own.
    Reported crime (orange) has a yearly rhythm and a gentle upward drift; recovery cases (aqua) fell by about half.
    Their sum (violet) peaked at {N['peak']} in {N['peak_month']} and inherits the decline of the second family. Two months
    stand out: April 2020 ({N['apr20']} cases), when the COVID-19 shutdown emptied the streets, and August 2024 ({N['aug24']}),
    the lowest in the series.</p>""")
    body.append(figure("hero", "The national total hides two opposite currents",
                       "Monthly cases. Thin lines: monthly values; thick lines: 3-month centred mean.",
                       "Hover for the month's values · click a legend item to hide a series · buttons zoom to recent years.", wide=True))
    body.append(keybox("Why it matters", "A headline saying “recorded crime fell” is technically true and practically misleading. "
                       "Everything that follows separates reported crime from police-initiated recovery cases."))
    body.append("</section>")

    body.append(chapter("rhythm", "Chapter 2 · Is there a normal year?", "The rhythm of an ordinary year",
                        "Crime in Bangladesh has a calendar: it climbs from February to a peak in May and June and falls to its lowest point in December."))
    body.append(f"""<p>Reported crime peaks in {N['seas_peak']} and bottoms out in {N['seas_trough']}, a swing of about
    {N['seas_amp']} between the strongest and weakest months; its STL seasonal strength is {N['seas_strength']} on a 0–1 scale.
    Switch the heatmap to recovery cases and the rhythm disappears, while the outlined August 2024 cell turns pale.</p>""")
    body.append(figure("calendar", "Calendar of crime: May peaks, December lulls, and the August 2024 hole",
                       "Monthly national cases (thousands for large series). Outlined cell: August 2024. Blank: not yet published.",
                       "Pick a series; hover a cell for the exact count."))
    body.append("""<p>Each crime has its own season. Woman and child repression rises from March and stays high until
    October; murder peaks in July; burglary and theft peak in August and September, the lean season before the main rice
    harvest. The averages use normal years only, so the shocks of 2020 and 2024 do not distort them; switch to all
    years to see how much those shocks move the profile.</p>""")
    body.append(figure("seasonal", "Every crime has a season",
                       "Average month-of-year index (each year's monthly mean = 100) with 95% confidence band.",
                       "Choose which years to average below the chart; hover a point for its index."))
    body.append("""<p>The STL decomposition separates trend, season and shock. Pick any series to see its trend step
    after August 2024 and the residual shocks of the lockdown months.</p>""")
    body.append(figure("stl", "Under the noise: trend, season and shock",
                       "Robust STL decomposition (period 12) of log monthly cases; seasonal and residual shown as % effects. Red dots: shocks above 15%.",
                       "Pick a series; hover any panel to read all four components for that month.", wide=True))
    body.append("""<p>Which crimes move together? Burglary, robbery, dacoity, kidnapping and theft rise and fall
    together. Narcotics, smuggling and arms recoveries form a separate block that correlates <em>negatively</em> with
    robbery and dacoity: months with more police searches tend to be months with less violent property crime. Compare
    the periods before and after the break to see how the blocks changed.</p>""")
    body.append(figure("correlation", "Which crimes move together?",
                       "Spearman rank correlation of monthly national counts, ordered by hierarchical clustering of the whole period.",
                       "Switch the period; hover a cell for the pair and its ρ."))
    body.append("</section>")

    body.append(chapter("pandemic", "Chapter 3 · 2020", "The pandemic pause",
                        "The lockdown showed what happens when policing and public life stop at the same time: almost everything recorded falls."))
    body.append(f"""<p>During the general holiday that began on 26 March 2020, recorded cases fell to {N['apr20']} in
    April 2020. Recovery cases fell furthest, to {N['rec_apr20']}, because police were redeployed to enforce the lockdown.
    By July 2020 the series had recovered (Figure {FIGS['hero']}). 2020 is a useful control: a collapse in recorded crime followed by a
    quick rebound is what a temporary pause looks like. August 2024 looks different.</p>""")
    body.append("</section>")

    body.append(chapter("rupture", "Chapter 4 · What changed, by how much, and for how long?", "Rupture: after the fifth of August",
                        "In July 2024 the protests appeared in the data as riots and assaults on police. In August, the recording system itself broke. When it came back, the country's crime mix had changed."))
    body.append(f"""<p>July 2024 recorded {N['riot_jul24']} riot cases and {N['pa_jul24']} police-assault cases, both the highest
    in the series. Then, after 5 August, recorded cases fell {N['aug_drop']} in one month, to {N['aug24']}. Narcotics recovery
    fell from {N['narco_jul24']} to {N['narco_aug24']} cases, yet murder cases jumped to {N['murder_aug24']}, the highest monthly
    figure on record. Each panel below shows one crime head with its 24-month mean before and after the break.</p>""")
    body.append(figure("small_multiples", "Sixteen crime heads, one break",
                       "Monthly national cases. Bars: mean of the 24 months before (Aug 2022 – Jul 2024) and after (Sep 2024 – Aug 2026). "
                       "% = change in means; stars = Mann–Whitney p (*** &lt; 0.001). Orange = rose, blue = fell.",
                       "Hover any line for the month; drag inside a panel to zoom.", wide=True))
    body.append(f"""<p>The before-and-after ledger adds uncertainty. Kidnapping more than doubled ({N['chg_Kidnapping']}),
    from {N['pre_Kidnapping']} to {N['post_Kidnapping']} cases a month; its Cliff's δ of {N['cliff_Kidnapping']} means every one
    of the 24 months after the break exceeded every one of the 24 months before. Dacoity rose {N['chg_Dacoity']} and
    robbery {N['chg_Robbery']}. Arms Act cases rose {N['chg_ArmsAct']}; narcotics fell {N['chg_Narcotics']}.</p>""")
    body.append(figure("forest", "The before-and-after ledger",
                       "Point: % change in mean monthly cases; bar: bootstrap 95% CI of the ratio. Grey: CI crosses zero. August 2024 itself excluded.",
                       "Hover a point for both means, the CI, the p-value and Cliff's δ."))
    body.append(f"""<p>Was it the break, or the trend? Segmented negative-binomial models control for the pre-existing
    trend, the season and the COVID months. They still find large immediate level changes: ×{N['irr_Kidnapping']} for
    kidnapping (95% CI {N['irrci_Kidnapping']}), ×{N['irr_Dacoity']} for dacoity ({N['irrci_Dacoity']}) and ×{N['irr_Robbery']}
    for robbery ({N['irrci_Robbery']}). For narcotics the level dropped to ×{N['irr_Narcotics']}.</p>""")
    body.append(figure("its", "Counting the gap: what the model expected without the break",
                       "log E[cases] = trend + post-break level + post-break slope + month effects + COVID and Aug-2024 dummies. "
                       "Shaded: modelled excess (orange) or shortfall (blue) against the no-break counterfactual.",
                       "Pick any of the 19 series; hover to compare observed, fitted and counterfactual values."))
    body.append(f"""<p>Two unsupervised methods agree on the timing without being told where to look. PELT places
    change points for dacoity in {N['cp_dac']}, kidnapping in {N['cp_kid']} and robbery in {N['cp_rob']}. Isolation Forest
    flags {N['anom_months']} as the most unusual months.</p>""")
    body.append(figure("anomalies", "Machines agree with history",
                       "Top: Isolation Forest anomaly score of each month's 15-head crime mix (red = flagged, contamination 6%). "
                       "Bottom: PELT change points (RBF cost) per series.",
                       "Hover a bar to see which crime heads made that month unusual.", wide=True))
    body.append(f"""<p>Murder needs care. Footnotes on the scans say {N['backlog_aug24']} of August 2024's {N['murder_aug24']}
    murder cases were for killings between 2009 and July 2024 that families had not been able to file; similar notes
    appear every month from February to September 2025, {N['backlog']} backlog cases in all. Remove them and the
    picture changes: raw murder is up {N['chg_Murder']}, but murder excluding backlog filings is up only {N['chg_MurderAdj']}
    (Mann–Whitney p = {N['p_murder_adj']}), with a model level change of ×{N['irr_MurderAdj']} (95% CI {N['irrci_MurderAdj']}).</p>""")
    body.append(figure("murder_backlog", "The murder spike is partly a paperwork spike",
                       "Monthly murder cases split by the footnotes that count delayed filings for older killings.",
                       "Hover a backlog bar to read the translated footnote · drag the strip below to change the period.", wide=True))
    body.append(f"""<p>Violent property crime moved to a new normal. From 2019 to 2023 the median month saw between
    {N['med_lo']} and {N['med_hi']} dacoity, robbery and kidnapping cases; in 2025 the median was {N['med25']}.</p>""")
    body.append(figure("ridgeline", "Violent property crime shifted right, and stayed there",
                       "Distribution of monthly national cases by year (density; ticks = individual months). 2026 = Jan–Aug.",
                       "Pick a series; hover a tick for its month."))
    body.append(figure("family_share", "The mix shifts: violent property crime claims a larger slice",
                       "Share of the ten named reactive crime heads (excludes “other cases” and recovery cases), 3-month rolling mean.",
                       "Hover for every family's share that month; click a legend item to highlight it."))
    body.append(figure("yoy", "Year against year",
                       "Change in national annual cases by crime head. Default: 2025, the first full year after the break, against 2023, the last full year before it.",
                       "Choose the comparison below the chart; hover a bar for both totals."))
    body.append(keybox("Chapter 4 in one sentence", "After 5 August 2024 Bangladesh recorded fewer cases overall because "
                       "police searched and seized less, while victims reported far more dacoity, robbery and kidnapping; "
                       "the apparent murder surge is mostly delayed filings."))
    body.append("</section>")

    body.append(chapter("geography", "Chapter 5 · Where did it happen?", "The geography of the break",
                        "The rise in violent crime reached every part of the country, but not equally."))
    body.append(f"""<p>Police units are grouped into the eight census divisions (each metro unit with its range) and
    divided by population. In 2025 reported crime per person was highest in {N['rate_hi_div']} ({N['rate_hi']} per 100,000)
    and lowest in {N['rate_lo_div']} ({N['rate_lo']}) and {N['rate_lo2_div']} ({N['rate_lo2']}). The change in violent crime is a
    different map: {N['violent_div_top']}, against {N['violent_div_low']}.</p>""")
    body.append('<div class="pair">')
    body.append(figure("map_rates", "Where crime is reported",
                       "Reported crime per 100,000 people per year, by division.",
                       "Pick a year; hover a division.",
                       source="Source: PHQ monthly crime statistics; population: BBS Census 2022 (adjusted)."))
    body.append(figure("map_change", "Where violence grew",
                       "Change in mean monthly cases, 24 months after vs 24 months before August 2024.",
                       "Pick a crime; hover a division."))
    body.append("</div>")
    body.append(f"""<p>{N['n_units_rose']} of the 17 police units recorded more violent crime after the break; the
    exception{'s are' if N['n_flat'] > 1 else ' is'} {N['unit_flat']}. In relative terms the biggest rises were
    {N['unit_top']}.</p>""")
    body.append(figure("dumbbell", "Nearly every unit saw more violent crime after the break",
                       "Mean monthly cases, 24 months before vs 24 months after August 2024 (log scale).",
                       "Pick a crime; hover a dot for the monthly mean."))
    body.append(figure("unit_heatmap", "Where the break hit: change by police unit and crime head",
                       "Mean monthly cases Sep 2024 – Aug 2026 against Aug 2022 – Jul 2024. Red = rise, blue = fall (colour capped at +200%). "
                       "Lines separate metro, range and railway police.",
                       "Hover a cell for the before and after means.", wide=True))
    top2 = (f" {N['top2_same']} hold the top two places in every year." if N["top2_same"] else "")
    body.append(f"""<p>Ranked by reported crime, the large district ranges lead.{top2} Hover a line to follow one unit;
    the animated race below replays the same ranking year by year.</p>""")
    body.append(figure("bump", "Who reports the most crime?",
                       "Rank of the 16 territorial units by annual reported crime (total minus recovery cases). Highlighted: DMP and the three biggest movers. *2026 annualised from Jan–Aug.",
                       "Hover a line or dot to follow one unit."))
    body.append(figure("race", "Reported crime by police unit, year by year",
                       "Annual reported crime per unit; 2026 annualised from January–August. Blue: metropolitan police; orange: range police.",
                       "Press Play, or drag the year slider."))
    body.append(f"""<p>Clustering the units by the <em>mix</em> of their caseload, not its size, gives three groups. The
    <strong>metro and port belt</strong> ({N['cl_Metro']}) over-indexes on narcotics, arms, robbery and burglary. The
    <strong>northern agrarian ranges</strong> ({N['cl_North']}) over-index on smuggling, consistent with their long land border.
    The <strong>Dhaka–Barishal ring</strong> ({N['cl_Dhaka']}) over-indexes on dacoity and kidnapping. The two PCA axes explain
    {N['pca_var']} of the variation; a silhouette of {N['sil']} says these are tendencies rather than sharp borders.</p>""")
    body.append(figure("clusters", "Three crime signatures",
                       "PCA of each unit's 2019–2026 crime mix (centred log-ratio of 15 head shares), coloured by k-means cluster (k = 3). Arrows: the eight heads that load most.",
                       "Hover a unit; click a legend item to hide a cluster."))
    body.append(figure("radar", "Three signatures, side by side",
                       "Share of each crime head in the cluster's caseload, indexed to the average unit (= 100).",
                       "Hover a vertex; click a legend item to hide a cluster."))
    body.append("</section>")

    body.append(chapter("future", "Chapter 6 · Where is it heading?", "A slow return?",
                        "Searches and seizures are rising again and violent crime is easing, but not yet back to where it was."))
    body.append(f"""<p>Comparing January–August 2026 with the same months of 2025, recovery cases are {N['ytdw_rec']},
    driven by narcotics ({N['ytd_narco']}): the strongest sign yet that proactive policing is returning, in the year of the
    12 February 2026 general election. At the same time dacoity is {N['ytdw_dac']}, murder {N['ytdw_mur']} and
    robbery {N['ytdw_rob']}.</p>""")
    body.append(ytd_table(N))
    body.append(figure("brush", "Overview and detail",
                       "Monthly national cases. Drag across the lower strip to choose the period shown above.",
                       "Drag or resize the grey window in the strip; hover the top chart for values; click a legend item to highlight."))
    body.append(f"""<p>SARIMAX models on log counts, with a regime dummy for the break and Fourier terms for the
    season, forecast {N['fc_next_total']} cases from {N['fc_first']} to {N['fc_last']} (last 12 months: {N['fc_last_total']}).
    Walk-forward backtests over the last 12 observed months beat a seasonal-naive forecast for every series: total cases
    {N['fc_mape_total']} mean absolute percentage error against {N['fc_naive_total']}, reported crime {N['fc_mape_rep']} against
    {N['fc_naive_rep']}.</p>""")
    body.append(figure("forecast", "What the next twelve months may hold",
                       "SARIMAX forecast with 80% and 95% intervals; orange: walk-forward one-step forecasts for the last 12 observed months.",
                       "Pick a series; zoom out to see the full history.", wide=True))
    body.append("</section>")



    src = R["src"]
    body.append(f"""
<section class="chapter" id="data">
  <p class="kicker">Data and methods</p>
  <h2>How this was made</h2>
  <p>Bangladesh Police Headquarters publishes its monthly crime statistics as scanned PDF tables. All 27 files
  covering {N['first']} – {N['last']} were downloaded, read with OCR and checked cell by cell against the printed row,
  column and recovery totals; the monthly tables for 2019–2023 add up exactly to the printed annual summaries. The
  result is one Excel file with {len(R['m']):,} rows ({N['months']} months × 17 police units), each tagged with the last day of
  its month (for example 30 Jun 2025). National figures on this site are the sum of the 17 units.</p>
  <p class="cta"><a class="btn" href="data/Bangladesh_Crime_Statistics_Jan2019-Aug2026.xlsx" download>Download the dataset (Excel)</a>
  <a class="btn ghost" href="{REPO}/tree/main/data/raw_pdf">Source PDFs ({N['n_pdf']} files)</a></p>
  <ul class="methods">
    <li><strong>Before and after:</strong> 24 months before (Aug 2022 – Jul 2024) against 24 months after (Sep 2024 – Aug 2026);
    August 2024 excluded. Mann–Whitney U, Cliff's δ, bootstrap 95% CI of the ratio of means.</li>
    <li><strong>Interrupted time series:</strong> negative-binomial GLM with trend, post-break level and slope, month effects and COVID / August-2024 dummies.</li>
    <li><strong>Seasonality:</strong> robust STL (period 12) on log counts.</li>
    <li><strong>Forecasting:</strong> SARIMAX on log counts, AIC-selected orders for d = 0 and d = 1, kept by walk-forward backtest.</li>
    <li><strong>Change points and anomalies:</strong> PELT (RBF cost, penalty 4); Isolation Forest (500 trees, contamination 6%).</li>
    <li><strong>Clustering:</strong> k-means (k = 3) on the centred log-ratio of each unit's crime mix; Railway Range left out as a one-unit outlier.</li>
    <li><strong>Caveat:</strong> these are cases recorded by police, not all crimes committed. Recording depends on victims coming forward and on police capacity.</li>
  </ul>
  <p>Charts are drawn with <strong>Plotly</strong> and <strong>Vega-Altair</strong>; the interactive overview at the top is the web version of the
  <strong>Dash</strong> dashboard (report Figure 24), rebuilt with Plotly.js so it runs in the browser. Charts that the printed report drew with <strong>matplotlib</strong> and
  <strong>seaborn</strong> are redrawn here with Plotly, because static images cannot be interactive. Every chart has its
  data as a CSV link below it.</p>
  {sources_table(src)}
</section>
</main>""")
    extra = ('<script defer src="https://cdn.jsdelivr.net/npm/vega@6"></script>\n'
             '<script defer src="https://cdn.jsdelivr.net/npm/vega-lite@6.4.1"></script>\n'
             '<script defer src="https://cdn.jsdelivr.net/npm/vega-embed@7"></script>\n'
             '<script defer src="assets/site.js"></script>\n'
             '<script defer src="assets/explorer.js"></script>')
    return (head("Fewer cases, more crime — Bangladesh 2019–2026",
                 "An interactive data story on Bangladesh Police crime statistics, January 2019 – August 2026.", extra)
            + '<body id="top">' + nav() + "".join(body) + footer() + "</body></html>")


def overview_html(N):
    """First screen: title, filters, eight tiles and eight charts in one viewport.

    Driven by assets/explorer.js (the web version of the Dash app). On a laptop or
    desktop the block is exactly one screen high; on phones it stacks and scrolls.
    """
    def card(cid, title, note="", key=False):
        note = (f'<span class="note key" id="{cid}-key"></span>' if key else
                f'<span class="note">{note}</span>' if note else "")
        return (f'<figure class="card"><figcaption title="{escape(title)}">{title}{note}</figcaption>'
                f'<div id="{cid}" class="ex-chart"></div></figure>')

    def total(kid, cap):
        return (f'<div class="tile sel"><div class="cap" id="{kid}-cap">{cap}</div>'
                f'<div class="big" id="{kid}"></div></div>')

    def change(kid):
        return (f'<div class="tile"><div class="big" id="{kid}"></div>'
                f'<div class="cap" id="{kid}-cap"></div></div>')
    return f"""
<section class="dash" id="overview" aria-label="Overview of the dataset">
  <div class="dash-top">
    <div class="dash-title">
      <h1>Fewer cases, more crime</h1>
      <p>Bangladesh Police crime statistics · {N['first']} – {N['last']} · {N['months']} months · 17 police units</p>
    </div>
    <div class="filters" aria-label="Filters for the overview">
      <label class="f"><span class="f-label">Period</span><select id="preset"></select></label>
      <label class="f"><span class="f-label">From</span><select id="from"></select></label>
      <label class="f"><span class="f-label">To</span><select id="to"></select></label>
      <details class="f multi" id="units-box"><summary><span class="f-label">Police units</span><span class="val" id="units-val">All units (national)</span></summary>
        <div class="opts" id="units"></div></details>
      <details class="f multi" id="heads-box"><summary><span class="f-label">Crime heads</span><span class="val" id="heads-val"></span></summary>
        <div class="opts" id="heads"></div></details>
    </div>
    <a class="story-link" href="#story">Read the story ↓</a>
  </div>
  <div class="dash-tiles">
    <div class="tgroup" aria-label="Totals for your selection">
      <span class="tg-label">Totals for your selection</span>
      {total("k-total", "Total cases")}
      {total("k-reported", "Reported crime (excl. recovery)")}
      {total("k-recovery", "Recovery cases (police-initiated)")}
      {total("k-heads", "Selected crime heads")}
    </div>
    <div class="tgroup" aria-label="What changed in your selection">
      <span class="tg-label">What changed in your selection</span>
      {change("k-drop")}
      {change("k-fewer")}
      {change("k-riser")}
      {change("k-murder")}
    </div>
  </div>
  <div class="dash-grid">
    {card("trend", "Selected heads, month by month", key=True)}
    {card("rr", "All cases: reported crime vs police-initiated recovery", key=True)}
    {card("years", "Selected heads, year by year", "Lighter bar: year with fewer months selected")}
    {card("units-bar", "Selected heads by police unit", "Highlighted: the units you picked")}
    {card("map", "Selected heads per 100,000 people a year", "By division; railway police not mapped")}
    {card("heat", "Selected heads by calendar month")}
    {card("fam", "Share of all cases by crime family")}
    {card("mix", "Every crime head (log scale)", "Coloured: the heads you picked")}
  </div>
</section>"""


def explorer_redirect():
    """The site used to have a separate explorer page; keep its link working."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Dashboard</title>'
            '<meta http-equiv="refresh" content="0; url=index.html#overview">'
            '<link rel="canonical" href="index.html#overview"></head><body>'
            '<p><a href="index.html#overview">The overview is on the main page.</a></p></body></html>')


def main():
    R = A.build()
    N = numbers(R)
    DOCS.mkdir(exist_ok=True)
    write_charts(R)
    write_explorer_data(R)
    (DOCS / "index.html").write_text(index_html(R, N), encoding="utf-8")
    (DOCS / "explorer.html").write_text(explorer_redirect(), encoding="utf-8")
    (DOCS / "assets").mkdir(exist_ok=True)
    for f in (HERE / "static").iterdir():
        shutil.copy(f, DOCS / "assets" / f.name)
    shutil.copy(A.XLSX, DOCS / "data" / A.XLSX.name)
    (DOCS / ".nojekyll").write_text("")
    print("site written to", DOCS)


if __name__ == "__main__":
    main()
