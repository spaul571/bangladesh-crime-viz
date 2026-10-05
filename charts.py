"""Every chart of the report, rebuilt as an interactive Plotly or Vega-Altair chart.

Each builder takes a theme T (theme.LIGHT / theme.DARK) and the analysis
bundle R (analysis.build()) and returns a Chart. Titles and subtitles are
written in the page HTML, so the charts carry no titles of their own.

Charts that were drawn with matplotlib or seaborn in the report are redrawn
here with Plotly (matplotlib and seaborn cannot be interactive in a browser);
the Plotly and Altair charts keep their library.

Controls: a Plotly chart may carry "controls", rendered by site.js as HTML
<select> elements above the chart. Each option holds Plotly.restyle patches
and one Plotly.relayout patch.
"""
from dataclasses import dataclass, field
import json

import altair as alt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

import analysis as A
from theme import (FONT, axis, plotly_layout, ramp_at, rgba, role, scale,
                   text_on, vega_config)

pio.templates.default = "none"
alt.data_transformers.disable_max_rows()

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LABEL = {A.REPORTED: "Reported crime (excl. recovery)", A.MURDER_ADJ: "Murder, excl. backlog filings",
         "Total Cases": "Total cases", "Recovery Total": "Recovery cases (all four)",
         "Woman & Child Repression": "Woman & child repression"}


def lab(s):
    return LABEL.get(s, s)


@dataclass
class Chart:
    kind: str                     # "plotly" | "vega"
    obj: object
    controls: list = field(default_factory=list)
    data: pd.DataFrame | None = None
    height: int = 480
    fit: str | None = None        # vega width fitting: "single" | "vconcat" | "facet"


def kfmt(v):
    if abs(v) < 1000:
        return f"{v:,.0f}"
    k = v / 1000
    return f"{k:,.0f}k" if abs(k - round(k)) < 1e-9 else f"{k:,.1f}k"


def events(fig, T, label=True, row=None, col=None, y=1.0):
    kw = {} if row is None else dict(row=row, col=col)
    fig.add_vrect(x0=A.COVID[0], x1=A.COVID[1], fillcolor=T.shade, line_width=0,
                  layer="below", **kw)
    fig.add_vline(x=pd.Timestamp("2024-08-05").timestamp() * 1000, line=dict(color=T.ink2, width=1),
                  layer="below", **kw)
    if label:
        for x, t in [(A.COVID[1] + pd.Timedelta(days=18), "COVID-19 shutdown"),
                     (pd.Timestamp("2024-08-25"), "5 Aug 2024<br>government falls")]:
            fig.add_annotation(x=x, y=y, yref="paper", text=t, showarrow=False, xanchor="left",
                               yanchor="top", align="left", font=dict(size=11, color=T.ink2))


def control(label, names, groups, n, layouts=None, default=0, always=()):
    """A <select> that shows one group of traces at a time."""
    opts = []
    for i, (name, idx) in enumerate(zip(names, groups)):
        vis = [(t in idx) or (t in always) for t in range(n)]
        opts.append({"label": name, "restyle": [[{"visible": vis}, list(range(n))]],
                     "relayout": (layouts[i] if layouts else {})})
    return {"label": label, "options": opts, "default": default}


def apply_default(fig, ctl):
    """Put the figure in the state of the control's default option (JS semantics)."""
    o = ctl["options"][ctl["default"]]
    for patch, idx in o["restyle"]:
        fig.plotly_restyle(patch, idx)
    if o["relayout"]:
        fig.plotly_relayout(o["relayout"])


def dropdown_style(T):
    return dict(bgcolor=T.surface, bordercolor=T.axis, font=dict(color=T.ink, size=12))


# ===========================================================================
# Chapter 1 - a country in numbers
# ===========================================================================
FAMILY = {"Dacoity": "Violent property", "Robbery": "Violent property",
          "Murder": "Violence against person", "Woman & Child Repression": "Violence against person",
          "Kidnapping": "Violence against person", "Speedy Trial": "Public order",
          "Riot": "Public order", "Police Assault": "Public order",
          "Burglary": "Property", "Theft": "Property", "Other Cases": "Other cases",
          "Arms Act": "Recovery (police-initiated)", "Explosive Act": "Recovery (police-initiated)",
          "Narcotics": "Recovery (police-initiated)", "Smuggling": "Recovery (police-initiated)"}


def sunburst(T, R):
    tot = R["nat"][A.HEADS].sum()
    g = pd.Series(FAMILY)
    gsum = tot.groupby(g).sum()
    gcol = {"Recovery (police-initiated)": role(T, "aqua"), "Other cases": T.context,
            "Violence against person": role(T, "orange"), "Property": role(T, "blue"),
            "Violent property": role(T, "red"), "Public order": role(T, "violet")}
    wrap = {"Recovery (police-initiated)": "Recovery<br>(police-initiated)",
            "Violence against person": "Violence<br>against person",
            "Woman & Child Repression": "Woman & child<br>repression",
            "Violent property": "Violent<br>property"}
    ids = ["All cases"] + list(gsum.index) + [f"{g[h]}/{h}" for h in A.HEADS]
    fig = go.Figure(go.Sunburst(
        ids=ids,
        labels=["All cases"] + [wrap.get(x, x) for x in gsum.index] + [wrap.get(h, h) for h in A.HEADS],
        parents=[""] + ["All cases"] * len(gsum) + [g[h] for h in A.HEADS],
        values=[tot.sum()] + list(gsum.values) + list(tot.values), branchvalues="total",
        marker=dict(colors=[T.surface] + [gcol[x] for x in gsum.index] + [gcol[g[h]] for h in A.HEADS],
                    line=dict(color=T.surface, width=2)),
        insidetextorientation="horizontal", textinfo="label+percent root",
        textfont=dict(size=13, family=FONT),
        hovertemplate="<b>%{value:,}</b> cases<br>%{label}<br>%{percentRoot:.1%} of all cases<extra></extra>",
        leaf=dict(opacity=0.8), sort=False))
    fig.update_layout(plotly_layout(T, margin=dict(l=4, r=4, t=4, b=4),
                                    uniformtext=dict(minsize=10, mode="hide")))
    data = pd.DataFrame({"crime_head": A.HEADS, "family": [g[h] for h in A.HEADS],
                         "cases": tot.values})
    return Chart("plotly", fig, data=data, height=600)


def hero(T, R):
    nat = R["nat"]
    fig = go.Figure()
    series = [("Total Cases", role(T, "violet"), "All recorded cases"),
              (A.REPORTED, role(T, "orange"), "Reported crime (victim-driven)"),
              ("Recovery Total", role(T, "aqua"), "Recovery cases (police-initiated)")]
    for col, c, name in series:
        y = nat[col]
        sm = y.rolling(3, center=True, min_periods=2).mean()
        fig.add_scatter(x=nat.index, y=y, name=name, legendgroup=name, showlegend=False,
                        line=dict(color=c, width=1), opacity=0.4,
                        hovertemplate=f"<b>%{{y:,}}</b> {name}<extra></extra>")
        fig.add_scatter(x=nat.index, y=sm, name=name, legendgroup=name,
                        line=dict(color=c, width=2.6, shape="spline", smoothing=0.6),
                        hoverinfo="skip")
        fig.add_annotation(x=nat.index[-1], y=sm.iloc[-2], text=name.split(" (")[0],
                           xanchor="right", yanchor="bottom", yshift=6, showarrow=False,
                           font=dict(size=12, color=T.ink))
    events(fig, T)
    tot = nat["Total Cases"]
    for d, txt, ax, ay in [(tot.idxmax(), f"Peak {tot.max():,} ({tot.idxmax():%b %Y})", 30, -30),
                           (pd.Timestamp("2020-04-30"), f"{tot.loc['2020-04-30']:,} in Apr 2020", 60, 46),
                           (pd.Timestamp("2024-08-31"), f"{tot.loc['2024-08-31']:,} in Aug 2024", -70, 34)]:
        fig.add_annotation(x=d, y=tot.loc[d], text=txt, ax=ax, ay=ay, showarrow=True, arrowhead=0,
                           arrowwidth=0.8, arrowcolor=T.muted, font=dict(size=11, color=T.ink2))
    fig.update_layout(plotly_layout(
        T, hovermode="x unified", margin=dict(l=52, r=16, t=64, b=40),
        legend=dict(orientation="h", x=0, y=1.1, xanchor="left", yanchor="bottom",
                    font=dict(size=12, color=T.ink2)),
        xaxis=axis(T, hoverformat="%B %Y", rangeselector=dict(
            buttons=[dict(count=2, label="2 years", step="year", stepmode="backward"),
                     dict(count=4, label="4 years", step="year", stepmode="backward"),
                     dict(step="all", label="All")],
            x=1, xanchor="right", y=1.1, yanchor="bottom", bgcolor=T.surface,
            activecolor=T.grid, bordercolor=T.axis, borderwidth=1, font=dict(color=T.ink2, size=11))),
        yaxis=axis(T, tickformat="~s", title="cases per month", rangemode="tozero",
                   showgrid=True)))
    data = nat[["Total Cases", A.REPORTED, "Recovery Total"]].reset_index()
    return Chart("plotly", fig, data=data, height=480)


# ===========================================================================
# Chapter 2 - the rhythm of an ordinary year
# ===========================================================================
CAL_SERIES = [A.REPORTED, "Recovery Total", "Total Cases"] + A.HEADS + [A.MURDER_ADJ]


def calendar(T, R):
    nat = R["nat"]
    years = sorted(nat.year.unique())
    fig = go.Figure()
    rows = []
    for i, s in enumerate(CAL_SERIES):
        p = pd.DataFrame({"y": nat.year, "m": nat.index.month, "v": nat[s]}).pivot(
            index="y", columns="m", values="v").reindex(columns=range(1, 13))
        big = p.max().max() >= 2000
        txt = p.map(lambda v: "" if pd.isna(v) else (f"{v / 1000:.1f}" if big else f"{v:.0f}"))
        lo, hi = np.nanmin(p.values), np.nanmax(p.values)
        cols = [["" if pd.isna(v) else text_on(ramp_at(T.seq, (v - lo) / (hi - lo or 1)))
                 for v in r] for r in p.values]
        fig.add_heatmap(
            z=p.values, x=MONTHS, y=[str(y) for y in years], text=txt.values,
            texttemplate="%{text}", textfont=dict(size=11), customdata=cols,
            colorscale=scale(T.seq), xgap=3, ygap=3, visible=(i == 0),
            hovertemplate=f"%{{x}} %{{y}}<br><b>%{{z:,}}</b> {lab(s)}<extra></extra>",
            colorbar=dict(thickness=10, outlinewidth=0, len=0.8, tickformat="~s",
                          tickfont=dict(color=T.ink2),
                          title=dict(text="thousand" if big else "cases", side="top",
                                     font=dict(color=T.ink2, size=11))),
            hoverongaps=False)
        rows.append(p.assign(series=s))
    fig.add_shape(type="rect", x0=6.5, x1=7.5, y0=years.index(2024) - 0.5,
                  y1=years.index(2024) + 0.5, line=dict(color=T.ink, width=2))
    fig.update_layout(plotly_layout(
        T, margin=dict(l=48, r=16, t=34, b=16),
        xaxis=axis(T, side="top", showgrid=False, type="category"),
        yaxis=axis(T, autorange="reversed", showgrid=False, type="category")))
    ctl = control("Series", [lab(s) for s in CAL_SERIES],
                  [[i] for i in range(len(CAL_SERIES))], len(fig.data))
    data = pd.concat(rows).reset_index().rename(columns={"y": "year"})
    return Chart("plotly", fig, [ctl], data=data, height=400)


def seasonal(T, R):
    nat = R["nat"]
    heads = ["Woman & Child Repression", "Murder", "Theft", "Burglary", "Robbery", "Dacoity",
             "Kidnapping", "Narcotics"]
    bases = {"Normal years only": [2019, 2021, 2022, 2023, 2025],
             "All full years": [2019, 2020, 2021, 2022, 2023, 2024, 2025]}
    rows = []
    for basis, yrs in bases.items():
        d = nat[nat.year.isin(yrs)]
        for h in heads:
            s = d[h]
            idx = s / s.groupby(s.index.year).transform("mean") * 100
            prof = idx.groupby(idx.index.month).agg(["mean", "std", "count"])
            for mth, r in prof.iterrows():
                se = 1.96 * r["std"] / np.sqrt(r["count"])
                rows.append(dict(basis=basis, crime=lab(h), month=MONTHS[mth - 1],
                                 idx=round(r["mean"], 1), lo=round(r["mean"] - se, 1),
                                 hi=round(r["mean"] + se, 1)))
    p = pd.DataFrame(rows)
    pick = alt.param(name="basis", value="Normal years only",
                     bind=alt.binding_radio(options=list(bases), name="Years averaged "))
    base = alt.Chart(p).transform_filter(alt.datum.basis == pick).encode(
        x=alt.X("month:O", sort=MONTHS, title=None,
                axis=alt.Axis(labelAngle=0, labelExpr="substring(datum.label,0,1)", ticks=False,
                              domain=False)))
    blue = role(T, "blue")
    band = base.mark_area(color=blue, opacity=0.2).encode(
        y=alt.Y("lo:Q", title=None, scale=alt.Scale(zero=False)), y2="hi:Q")
    line = base.mark_line(color=blue, strokeWidth=2.2,
                          point=alt.OverlayMarkDef(size=36, color=blue, filled=True)).encode(
        y="idx:Q",
        tooltip=[alt.Tooltip("crime:N", title="Crime"), alt.Tooltip("month:O", title="Month"),
                 alt.Tooltip("idx:Q", title="Index (year mean = 100)", format=".0f"),
                 alt.Tooltip("lo:Q", title="95% CI low", format=".0f"),
                 alt.Tooltip("hi:Q", title="95% CI high", format=".0f")])
    ref = alt.Chart(p).transform_filter(alt.datum.basis == pick).mark_rule(
        color=T.ink2, strokeWidth=0.8, strokeDash=[3, 3]).encode(y=alt.datum(100))
    chart = alt.layer(band, ref, line).properties(width=180, height=130).facet(
        facet=alt.Facet("crime:N", sort=[lab(h) for h in heads], title=None,
                        header=alt.Header(labelFontSize=12, labelFontWeight=600, labelAnchor="start",
                                          labelColor=T.ink)),
        columns=4).resolve_scale(y="independent").add_params(pick)
    return Chart("vega", chart, data=p, height=420, fit="facet")


def stl(T, R):
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.035,
                        row_heights=[0.32, 0.26, 0.21, 0.21])
    groups, rows = [], []
    for s in A.SERIES:
        d = R["stl"][s]
        i0 = len(fig.data)
        fig.add_scatter(x=d.index, y=d.observed, line=dict(color=role(T, "blue"), width=1.8),
                        name="Observed", hovertemplate="<b>%{y:,}</b> observed<extra></extra>",
                        row=1, col=1)
        fig.add_scatter(x=d.index, y=d.trend, line=dict(color=role(T, "violet"), width=2.4),
                        name="Trend", hovertemplate="<b>%{y:,.0f}</b> trend<extra></extra>",
                        row=2, col=1)
        fig.add_bar(x=d.index, y=d.seasonal_pct, name="Seasonal",
                    marker=dict(color=np.where(d.seasonal_pct >= 0, role(T, "orange"),
                                               role(T, "blue")).tolist(), line_width=0),
                    hovertemplate="<b>%{y:+.1f}%</b> seasonal effect<extra></extra>", row=3, col=1)
        fig.add_scatter(x=d.index, y=d.resid_pct, mode="markers", name="Residual",
                        marker=dict(size=7, color=np.where(d.resid_pct.abs() > 15, role(T, "red"),
                                                           T.muted).tolist(),
                                    line=dict(color=T.surface, width=1)),
                        hovertemplate="<b>%{y:+.1f}%</b> residual (shock)<extra></extra>",
                        row=4, col=1)
        groups.append(list(range(i0, len(fig.data))))
        rows.append(d.assign(series=s))
    for r in range(1, 5):
        events(fig, T, label=(r == 1), row=r, col=1)
    fig.add_hline(y=0, line=dict(color=T.axis, width=0.8), row=4, col=1)
    fig.update_layout(plotly_layout(T, showlegend=False, hovermode="x unified", bargap=0.15,
                                    margin=dict(l=70, r=16, t=16, b=36)))
    names = ["Observed", "Trend", "Seasonal, %", "Residual, %"]
    for r in range(1, 5):
        fig.update_yaxes(axis(T, showgrid=True, title=dict(text=names[r - 1], font=dict(size=11)),
                              tickformat="~s" if r < 3 else ".0f"), row=r, col=1)
        fig.update_xaxes(axis(T, hoverformat="%B %Y"), row=r, col=1)
    ctl = control("Series", [lab(s) for s in A.SERIES], groups, len(fig.data),
                  default=A.SERIES.index(A.REPORTED),
                  always=[i for i, t in enumerate(fig.data) if t.name is None])
    apply_default(fig, ctl)
    data = pd.concat(rows).reset_index()
    return Chart("plotly", fig, [ctl], data=data, height=640)


def correlation(T, R):
    from scipy.cluster.hierarchy import leaves_list, linkage
    nat = R["nat"]
    full = nat[A.HEADS].astype(float).corr(method="spearman")
    order = [A.HEADS[i] for i in leaves_list(linkage(full.values, method="average"))]
    periods = {"Whole period (Jan 2019 – Aug 2026)": nat,
               "Before the break (Jan 2019 – Jul 2024)": nat.loc[:"2024-07-31"],
               "After the break (Sep 2024 – Aug 2026)": nat.loc["2024-09-30":]}
    fig = go.Figure()
    rows = []
    for i, (name, d) in enumerate(periods.items()):
        c = d[order].astype(float).corr(method="spearman")
        fig.add_heatmap(z=c.values, x=[lab(h) for h in order], y=[lab(h) for h in order],
                        zmin=-1, zmax=1, colorscale=scale(T.div), xgap=2, ygap=2,
                        text=np.vectorize(lambda v: f"{v:.2f}")(c.values),
                        texttemplate="%{text}", textfont=dict(size=10), visible=(i == 0),
                        hovertemplate="%{y} × %{x}<br>Spearman ρ <b>%{z:.2f}</b><extra></extra>",
                        colorbar=dict(thickness=10, outlinewidth=0, len=0.6, tickvals=[-1, 0, 1],
                                      tickfont=dict(color=T.ink2),
                                      title=dict(text="ρ", side="top", font=dict(color=T.ink2))))
        rows.append(c.stack().rename("rho").reset_index().assign(period=name))
    fig.update_layout(plotly_layout(
        T, margin=dict(l=160, r=16, t=8, b=150),
        xaxis=axis(T, tickangle=-45, showgrid=False),
        yaxis=axis(T, autorange="reversed", showgrid=False)))
    ctl = control("Period", list(periods), [[0], [1], [2]], 3)
    data = pd.concat(rows).rename(columns={"level_0": "head_a", "level_1": "head_b"})
    return Chart("plotly", fig, [ctl], data=data, height=660)


# ===========================================================================
# Chapter 4 - rupture
# ===========================================================================
def stars(p):
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."


def small_multiples(T, R):
    nat, pp = R["nat"], R["pp"]
    order = pp.loc[A.HEADS + [A.MURDER_ADJ], "pct_change"].sort_values(ascending=False).index
    titles = [f"<b>{lab(s).replace('Murder, excl. backlog filings', 'Murder, excl. backlog')}</b>"
              f"  {pp.loc[s, 'pct_change']:+.0f}%".replace("-", "−") + f" {stars(pp.loc[s, 'p_value'])}"
              for s in order]
    fig = make_subplots(rows=4, cols=4, shared_xaxes=True, subplot_titles=titles,
                        vertical_spacing=0.075, horizontal_spacing=0.05)
    for k, s in enumerate(order):
        r, c = k // 4 + 1, k % 4 + 1
        y = nat[s]
        pre, post = pp.loc[s, "pre_mean"], pp.loc[s, "post_mean"]
        col = role(T, "orange") if post > pre else role(T, "blue")
        fig.add_scatter(x=nat.index, y=y, line=dict(color=T.context, width=1.2), row=r, col=c,
                        hovertemplate=f"%{{x|%b %Y}}<br><b>%{{y:,}}</b> {lab(s)}<extra></extra>")
        tail = nat.loc[A.POST[0]:]
        fig.add_scatter(x=tail.index, y=tail[s], line=dict(color=col, width=1.8), row=r, col=c,
                        hovertemplate=f"%{{x|%b %Y}}<br><b>%{{y:,}}</b> {lab(s)}<extra></extra>")
        fig.add_scatter(x=[A.PRE[0], A.PRE[1]], y=[pre, pre], mode="lines", row=r, col=c,
                        line=dict(color=T.ink2, width=2),
                        hovertemplate=f"Mean before: <b>{pre:,.1f}</b>/month<extra></extra>")
        fig.add_scatter(x=[A.POST[0], A.POST[1]], y=[post, post], mode="lines", row=r, col=c,
                        line=dict(color=T.ink, width=2),
                        hovertemplate=f"Mean after: <b>{post:,.1f}</b>/month<extra></extra>")
        fig.add_vline(x=pd.Timestamp("2024-08-05").timestamp() * 1000,
                      line=dict(color=T.muted, width=0.8), row=r, col=c)
        fig.update_yaxes(axis(T, showgrid=True, tickformat="~s", range=[0, y.max() * 1.15],
                              tickfont=dict(size=10, color=T.ink2)), row=r, col=c)
        fig.update_xaxes(axis(T, dtick="M24", tickformat="%Y", tickfont=dict(size=10, color=T.ink2)),
                         row=r, col=c)
    for a in fig.layout.annotations:
        a.font = dict(size=12, color=T.ink)
        a.xanchor, a.x = "left", a.x - 0.105
    fig.update_layout(plotly_layout(T, showlegend=False, margin=dict(l=40, r=12, t=36, b=30)))
    data = pp.loc[order].reset_index()
    return Chart("plotly", fig, data=data, height=860)


def forest(T, R):
    pp = R["pp"].copy()
    keep = A.HEADS + [A.MURDER_ADJ, A.REPORTED, "Recovery Total", "Total Cases"]
    pp = pp.loc[keep].sort_values("pct_change")
    pp["lo"], pp["hi"] = (pp.ratio_lo - 1) * 100, (pp.ratio_hi - 1) * 100
    XMAX = 160
    up, down, grey = role(T, "orange"), role(T, "blue"), T.context
    pp["col"] = np.where((pp.ratio_lo < 1) & (pp.ratio_hi > 1), grey,
                         np.where(pp["pct_change"] > 0, up, down))
    labels = [f"<b>{lab(s)}</b>" if s in (A.REPORTED, "Recovery Total", "Total Cases") else lab(s)
              for s in pp.index]
    fig = go.Figure()
    for c in (up, down, grey):
        sub = pp[pp.col == c]
        xs, ys = [], []
        for s, r in sub.iterrows():
            xs += [r.lo, min(r.hi, XMAX), None]
            ys += [labels[list(pp.index).index(s)]] * 2 + [None]
        fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=c, width=4),
                        opacity=0.55, hoverinfo="skip", showlegend=False)
    clipped = pp[pp.hi > XMAX]
    fig.add_scatter(x=[XMAX] * len(clipped), y=[labels[list(pp.index).index(s)] for s in clipped.index],
                    mode="markers", marker=dict(symbol="triangle-right", size=10, color=T.context),
                    hoverinfo="skip", showlegend=False)
    custom = np.stack([pp.pre_mean, pp.post_mean, pp.lo, pp.hi, pp.p_value, pp.cliffs_delta], axis=1)
    fig.add_scatter(
        x=pp["pct_change"], y=labels, mode="markers+text", customdata=custom,
        marker=dict(size=13, color=pp.col.tolist(), line=dict(color=T.surface, width=2)),
        text=[f"{v:+.0f}%" for v in pp["pct_change"]], textposition="top center",
        textfont=dict(size=11, color=T.ink), showlegend=False,
        hovertemplate=("<b>%{x:+.1f}%</b> %{y}<br>Mean before: %{customdata[0]:,.1f}/month"
                       "<br>Mean after: %{customdata[1]:,.1f}/month<br>95% CI: %{customdata[2]:+.0f}% "
                       "to %{customdata[3]:+.0f}%<br>Mann–Whitney p = %{customdata[4]:.3g}"
                       "<br>Cliff's δ = %{customdata[5]:.2f}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=T.ink2, width=1))
    fig.update_layout(plotly_layout(
        T, margin=dict(l=210, r=24, t=12, b=48),
        xaxis=axis(T, showgrid=True, ticksuffix="%", range=[-70, XMAX + 12], zeroline=False,
                   title=dict(text="change in mean monthly cases, 24 months after vs 24 months before",
                              font=dict(size=12, color=T.ink2))),
        yaxis=axis(T, showgrid=False, categoryorder="array", categoryarray=labels)))
    data = pp.drop(columns=["col"]).reset_index()
    return Chart("plotly", fig, data=data, height=700)


ITS_ORDER = ["Kidnapping", "Dacoity", "Robbery", "Narcotics"]


def its(T, R):
    fit, itsr, nat = R["itsfit"], R["its"], R["nat"]
    opts = ITS_ORDER + [s for s in A.SERIES if s not in ITS_ORDER]
    fig = go.Figure()
    groups, layouts = [], []
    post = fit.index > A.BREAK
    for k, s in enumerate(opts):
        r = itsr.loc[s]
        col = role(T, "orange") if r.irr_post > 1 else role(T, "blue")
        i0 = len(fig.data)
        first = k == 0
        fig.add_scatter(x=nat.index, y=nat[s], mode="markers", name="Observed",
                        legendgroup="obs", showlegend=first,
                        marker=dict(size=6, color=T.muted, line=dict(color=T.surface, width=1)),
                        hovertemplate="<b>%{y:,}</b> observed<extra></extra>")
        fig.add_scatter(x=fit.index[~post], y=fit[f"fit::{s}"][~post], name="Model fit",
                        legendgroup="fit", showlegend=first, line=dict(color=T.ink2, width=1.8),
                        hovertemplate="<b>%{y:,.0f}</b> model<extra></extra>")
        fig.add_scatter(x=fit.index[post], y=fit[f"cf::{s}"][post], name="Counterfactual (no break)",
                        legendgroup="cf", showlegend=first,
                        line=dict(color=T.ink2, width=1.6, dash="dot"),
                        hovertemplate="<b>%{y:,.0f}</b> without the break<extra></extra>")
        fig.add_scatter(x=fit.index[post], y=fit[f"fit::{s}"][post], name="Model fit after the break",
                        legendgroup="fit", showlegend=False, line=dict(color=col, width=2.6),
                        fill="tonexty", fillcolor=rgba(col, 0.18),
                        hovertemplate="<b>%{y:,.0f}</b> model<extra></extra>")
        groups.append(list(range(i0, len(fig.data))))
        layouts.append({"annotations[2].text":
                        f"<b>{lab(s)}</b><br>Level change ×{r.irr_post:.2f}"
                        f"<br>95% CI {r.irr_post_lo:.2f}–{r.irr_post_hi:.2f}",
                        "yaxis.range": [0, nat[s].max() * 1.15]})
    events(fig, T)
    fig.add_annotation(x=0.01, y=0.97, xref="paper", yref="paper", text="", showarrow=False,
                       xanchor="left", yanchor="top", align="left", bgcolor=T.surface,
                       bordercolor=T.grid, borderpad=6, font=dict(size=12, color=T.ink))
    fig.update_layout(plotly_layout(
        T, hovermode="x unified", margin=dict(l=52, r=16, t=40, b=40),
        xaxis=axis(T, hoverformat="%B %Y"),
        yaxis=axis(T, showgrid=True, tickformat="~s", title="cases per month")))
    ctl = control("Crime head", [lab(s) for s in opts], groups, len(fig.data), layouts)
    apply_default(fig, ctl)
    data = fit.reset_index()
    return Chart("plotly", fig, [ctl], data=data, height=500)


def anomalies(T, R):
    an, cp, nat = R["an"], R["cp"], R["nat"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.42, 0.58],
                        vertical_spacing=0.06)
    fig.add_bar(x=an.date, y=an.score, customdata=np.stack([an.drivers], axis=1),
                marker=dict(color=np.where(an.flag, role(T, "red"), T.context).tolist(),
                            line_width=0),
                hovertemplate="%{x|%B %Y}<br>Anomaly score <b>%{y:.3f}</b><br>"
                              "Most unusual: %{customdata[0]}<extra></extra>", row=1, col=1)
    flagged = an[an.flag].sort_values("date").reset_index(drop=True)
    for i, r in flagged.iterrows():
        close = i > 0 and (r.date - flagged.date[i - 1]).days < 200
        fig.add_annotation(x=r.date, y=r.score, text=f"{r.date:%b %Y}", showarrow=close,
                           ay=-24 if close else 0, ax=0, yshift=0 if close else 10, arrowwidth=0.6,
                           arrowcolor=T.muted, font=dict(size=10, color=T.ink), row=1, col=1)
    series = list(dict.fromkeys(cp.series))
    for i, s in enumerate(series):
        fig.add_scatter(x=[nat.index[0], nat.index[-1]], y=[lab(s)] * 2, mode="lines",
                        line=dict(color=T.grid, width=7), hoverinfo="skip", row=2, col=1)
        pts = cp[cp.series == s]
        fig.add_scatter(x=pts.date, y=[lab(s)] * len(pts), mode="markers+text",
                        text=[f"{d:%b %y}" for d in pts.date], textposition="top center",
                        textfont=dict(size=9, color=T.ink2),
                        marker=dict(size=12, color=role(T, "violet"), line=dict(color=T.surface, width=2)),
                        hovertemplate=f"{lab(s)}<br>change point <b>%{{x|%B %Y}}</b><extra></extra>",
                        row=2, col=1)
    for r in (1, 2):
        events(fig, T, label=False, row=r, col=1)
    fig.update_layout(plotly_layout(T, showlegend=False, bargap=0.12,
                                    margin=dict(l=190, r=16, t=16, b=36)))
    fig.update_yaxes(axis(T, showgrid=True, title=dict(text="anomaly score", font=dict(size=11)),
                          range=[an.score.min() * 0.95, an.score.max() * 1.12]), row=1, col=1)
    fig.update_yaxes(axis(T, showgrid=False, autorange="reversed",
                          categoryorder="array", categoryarray=[lab(s) for s in series]), row=2, col=1)
    fig.update_xaxes(axis(T), row=2, col=1)
    data = an.merge(cp.assign(change_point_in=cp.series).groupby("date").change_point_in
                    .agg(", ".join).reset_index(), on="date", how="left")
    return Chart("plotly", fig, data=data, height=660)


def murder_backlog(T, R):
    nat = R["nat"]
    recent, bl = nat[A.MURDER_ADJ], nat.backlog_murder_cases
    fig = go.Figure()
    fig.add_bar(x=nat.index, y=recent, name="Recent incidents", marker=dict(color=role(T, "blue"),
                                                                             line_width=0),
                hovertemplate="<b>%{y:,}</b> recent incidents<extra></extra>")
    fig.add_bar(x=nat.index, y=bl.where(bl > 0), name="Backlog filings for older incidents",
                marker=dict(color=role(T, "orange"), line=dict(color=T.surface, width=1.5)),
                text=[f"{v}" if v > 0 else "" for v in bl], textposition="outside",
                textfont=dict(size=10, color=T.ink2), cliponaxis=False,
                customdata=np.stack([nat.backlog_note.str.wrap(60).str.replace("\n", "<br>")], axis=1),
                hovertemplate="<b>%{y:,}</b> backlog filings<br><i>%{customdata[0]}</i><extra></extra>")
    fig.add_vline(x=pd.Timestamp("2024-08-05").timestamp() * 1000, line=dict(color=T.ink2, width=1))
    fig.add_annotation(x=pd.Timestamp("2024-07-20"), y=0.98, yref="y domain",
                       text=f"Aug 2024: {nat.loc['2024-08-31', 'Murder']:,} murder cases,<br>"
                            f"{bl.loc['2024-08-31']} of them for incidents<br>from 2009 – Jul 2024",
                       showarrow=False, xanchor="right", yanchor="top", align="right",
                       font=dict(size=11, color=T.ink2))
    fig.update_layout(plotly_layout(
        T, barmode="stack", bargap=0.18, hovermode="x unified",
        margin=dict(l=52, r=16, t=40, b=40),
        xaxis=axis(T, range=[pd.Timestamp("2022-12-10"), pd.Timestamp("2026-09-20")],
                   hoverformat="%B %Y", rangeslider=dict(visible=True, thickness=0.07,
                                                          bgcolor=T.surface, bordercolor=T.grid)),
        yaxis=axis(T, showgrid=True, range=[0, 720], title="murder cases per month")))
    data = nat[["Murder", A.MURDER_ADJ, "backlog_murder_cases", "backlog_note"]].reset_index()
    return Chart("plotly", fig, data=data, height=520)


def ridgeline(T, R):
    nat = R["nat"]
    opts = {"Dacoity + robbery + kidnapping": nat[["Dacoity", "Robbery", "Kidnapping"]].sum(axis=1),
            "Dacoity": nat.Dacoity, "Robbery": nat.Robbery, "Kidnapping": nat.Kidnapping,
            "Murder, excl. backlog filings": nat[A.MURDER_ADJ]}
    years = sorted(nat.year.unique())
    col = {y: T.context for y in years}
    col.update({2024: role(T, "yellow"), 2025: role(T, "orange"), 2026: role(T, "red")})
    fig = go.Figure()
    groups, layouts, rows = [], [], []
    for name, s in opts.items():
        i0 = len(fig.data)
        anns = []
        for y in years:
            v = s[s.index.year == y]
            fig.add_violin(x=v.values, y=[str(y)] * len(v), orientation="h", side="positive",
                           width=1.9, spanmode="hard", points="all", pointpos=-0.12, jitter=0,
                           line=dict(color=T.surface if T.name == "light" else col[y], width=1.2),
                           fillcolor=rgba(col[y], 0.85) if col[y].startswith("#") else col[y],
                           marker=dict(size=5, color=T.ink2, symbol="line-ns-open", line_width=1),
                           text=[f"{d:%b %Y}" for d in v.index], hoveron="points",
                           hovertemplate="%{text}: <b>%{x:,}</b><extra></extra>",
                           name=str(y), showlegend=False, meanline=dict(visible=False))
            anns.append(dict(x=0.005, xref="paper", y=len(years) - 1 - years.index(y), yref="y",
                             yshift=9, xanchor="left",
                             text=f"median {np.median(v):,.0f}/month", showarrow=False,
                             font=dict(size=11, color=T.ink2)))
            rows.append(pd.DataFrame({"series": name, "date": v.index, "cases": v.values}))
        groups.append(list(range(i0, len(fig.data))))
        layouts.append({"annotations": anns})
    fig.update_layout(plotly_layout(
        T, violingap=0, margin=dict(l=48, r=16, t=12, b=48),
        xaxis=axis(T, showgrid=True, rangemode="tozero", title="cases per month (national)"),
        yaxis=axis(T, showgrid=False, type="category", categoryorder="array",
                   categoryarray=[str(y) for y in years[::-1]], range=[-0.5, len(years) - 0.1])))
    ctl = control("Series", list(opts), groups, len(fig.data), layouts)
    apply_default(fig, ctl)
    return Chart("plotly", fig, [ctl], data=pd.concat(rows), height=560)


FAM10 = {"Murder": "Violence against person", "Woman & Child Repression": "Violence against person",
         "Kidnapping": "Violence against person", "Dacoity": "Violent property crime",
         "Robbery": "Violent property crime", "Burglary": "Property crime", "Theft": "Property crime",
         "Speedy Trial": "Public order", "Riot": "Public order", "Police Assault": "Public order"}


def family_share(T, R):
    nat = R["nat"]
    d = nat[list(FAM10)].rolling(3, min_periods=1).mean()
    d = d.T.groupby(pd.Series(FAM10)).sum().T
    d = d.div(d.sum(axis=1), axis=0).reset_index().melt("date", var_name="family", value_name="share")
    d["date"] = d.date.dt.strftime("%Y-%m-%d")
    d["share"] = d.share.round(5)
    dom = ["Violence against person", "Violent property crime", "Property crime", "Public order"]
    rng = [role(T, "orange"), role(T, "red"), role(T, "blue"), role(T, "violet")]
    legend = alt.selection_point(fields=["family"], bind="legend")
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False,
                                clear="pointerout")
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%Y", tickCount="year", grid=False))
    area = alt.Chart(d).mark_area(interpolate="monotone", stroke=T.surface, strokeWidth=1).encode(
        x=x, y=alt.Y("share:Q", stack="normalize", title="share of the ten named crime heads",
                     axis=alt.Axis(format="%", grid=False)),
        color=alt.Color("family:N", scale=alt.Scale(domain=dom, range=rng),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal")),
        order=alt.Order("family:N", sort="ascending"),
        opacity=alt.condition(legend, alt.value(1), alt.value(0.25))).add_params(legend)
    rule = alt.Chart(d).transform_pivot("family", value="share", groupby=["date"]).mark_rule(
        color=T.ink, strokeWidth=1.2).encode(
        x=x, opacity=alt.condition(hover, alt.value(0.9), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", format="%B %Y", title="Month")] +
                [alt.Tooltip(f"{f}:Q", format=".1%") for f in dom]).add_params(hover)
    brk = pd.DataFrame({"d": ["2024-08-05"], "t": ["5 Aug 2024"]})
    mark = alt.Chart(brk).mark_rule(color=T.ink, strokeWidth=1, strokeDash=[4, 3]).encode(x="d:T")
    txt = alt.Chart(brk).mark_text(align="right", dx=-5, dy=8, color=T.ink, fontSize=11,
                                   baseline="top").encode(x="d:T", y=alt.value(0), text="t:N")
    chart = (area + mark + txt + rule).properties(width="container", height=360)
    return Chart("vega", chart, data=d, height=420, fit="single")


def yoy(T, R):
    nat = R["nat"]
    ann = nat.groupby("year")[A.HEADS].sum()
    pairs = [(2025, 2023), (2025, 2024), (2024, 2023), (2023, 2022), (2022, 2021), (2021, 2020),
             (2020, 2019)]
    rows = []
    for a, b in pairs:
        for h in A.HEADS:
            rows.append(dict(pair=f"{a} vs {b}", crime=lab(h), base=int(ann.loc[b, h]),
                             new=int(ann.loc[a, h]), chg=(ann.loc[a, h] / ann.loc[b, h] - 1) * 100))
    ya = nat.loc["2025-01-31":"2025-08-31", A.HEADS].sum()
    yb = nat.loc["2026-01-31":"2026-08-31", A.HEADS].sum()
    for h in A.HEADS:
        rows.append(dict(pair="Jan–Aug 2026 vs Jan–Aug 2025", crime=lab(h), base=int(ya[h]),
                         new=int(yb[h]), chg=(yb[h] / ya[h] - 1) * 100))
    d = pd.DataFrame(rows)
    d["chg"] = d.chg.round(1)
    d["dir"] = np.where(d.chg >= 0, "Rose", "Fell")
    d["label"] = d.chg.map(lambda v: f"{v:+.0f}%".replace("-", "−"))
    opts = list(dict.fromkeys(d.pair))
    pick = alt.param(name="pair", value=opts[0], bind=alt.binding_select(options=opts, name="Compare "))
    base = alt.Chart(d).transform_filter(alt.datum.pair == pick).encode(
        y=alt.Y("crime:N", sort=alt.EncodingSortField(field="chg", op="max", order="descending"), title=None,
                axis=alt.Axis(domain=False, ticks=False, labelPadding=8, labelColor=T.ink)))
    bars = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.72}).encode(
        x=alt.X("chg:Q", title="change in annual cases (%)", axis=alt.Axis(grid=True, format="+d")),
        color=alt.Color("dir:N", scale=alt.Scale(domain=["Rose", "Fell"],
                                                 range=[role(T, "orange"), role(T, "blue")]),
                        legend=alt.Legend(title=None, orient="bottom-right")),
        tooltip=[alt.Tooltip("crime:N", title="Crime"), alt.Tooltip("pair:N", title="Comparison"),
                 alt.Tooltip("base:Q", format=",", title="Earlier"),
                 alt.Tooltip("new:Q", format=",", title="Later"),
                 alt.Tooltip("chg:Q", format="+.1f", title="Change, %")])
    pos = base.transform_filter(alt.datum.chg >= 0).mark_text(
        align="left", dx=5, fontSize=11, color=T.ink).encode(x="chg:Q", text="label:N")
    neg = base.transform_filter(alt.datum.chg < 0).mark_text(
        align="right", dx=-5, fontSize=11, color=T.ink).encode(x="chg:Q", text="label:N")
    rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=T.ink2).encode(x="x:Q")
    chart = (bars + pos + neg + rule).add_params(pick).properties(width="container", height=430)
    return Chart("vega", chart, data=d, height=500, fit="single")


# ===========================================================================
# Chapter 5 - geography
# ===========================================================================
ISO = {"Barishal": "BD-A", "Chattogram": "BD-B", "Dhaka": "BD-C", "Khulna": "BD-D",
       "Rajshahi": "BD-E", "Rangpur": "BD-F", "Sylhet": "BD-G", "Mymensingh": "BD-H"}
ANCHOR = {"Rangpur": (89.15, 25.75), "Rajshahi": (88.85, 24.5), "Mymensingh": (90.3, 24.9),
          "Sylhet": (91.75, 24.55), "Dhaka": (90.15, 23.7), "Khulna": (89.2, 22.85),
          "Barishal": (90.35, 22.25), "Chattogram": (91.85, 22.6)}


def _geo():
    geo = json.load(open(A.HERE / "data" / "bgd_adm1.geojson"))

    def area(ring):
        a = np.asarray(ring)
        return 0.5 * np.sum(a[:-1, 0] * a[1:, 1] - a[1:, 0] * a[:-1, 1])
    # d3-geo needs clockwise exterior rings, or a polygon floods the globe
    for f in geo["features"]:
        g = f["geometry"]
        for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            for i, ring in enumerate(poly):
                cw = area(ring) < 0
                if (i == 0 and not cw) or (i > 0 and cw):
                    poly[i] = ring[::-1]
        f["properties"] = {"shapeISO": f["properties"]["shapeISO"]}
    return geo


GEO = _geo()
DIVS = list(ISO)


def _map_fig(T, z, zmin, zmax, colors, hover, cbar, zmid=None):
    fig = go.Figure()
    fig.add_choropleth(geojson=GEO, featureidkey="properties.shapeISO",
                       locations=[ISO[d] for d in DIVS], z=z, zmin=zmin, zmax=zmax, zmid=zmid,
                       colorscale=scale(colors), marker_line_color=T.surface, marker_line_width=2,
                       customdata=DIVS, hovertemplate=hover,
                       colorbar=dict(thickness=10, outlinewidth=0, len=0.6, x=0.98,
                                     tickfont=dict(color=T.ink2), **cbar))
    fig.add_scattergeo(lon=[ANCHOR[d][0] for d in DIVS], lat=[ANCHOR[d][1] for d in DIVS],
                       mode="text", text=[""] * 8, hoverinfo="skip", showlegend=False,
                       textfont=dict(size=12, family=FONT, shadow="auto"))
    fig.update_geos(fitbounds="locations", visible=False, bgcolor=T.surface, projection_type="mercator")
    fig.update_layout(plotly_layout(T, margin=dict(l=0, r=0, t=0, b=0)))
    return fig


def _labels(T, vals, fmt, colors, lo, hi):
    return ([f"<b>{d}</b><br>{fmt.format(vals[d])}" for d in DIVS],
            [text_on(ramp_at(colors, (vals[d] - lo) / (hi - lo))) for d in DIVS])


def map_rates(T, R):
    div = R["div"]
    col = f"rate::{A.REPORTED}"
    piv = div.pivot(index="year", columns="division", values=col)
    lo, hi = 0, float(np.ceil(piv.values.max() / 10) * 10)
    colors = T.seq[1:11] if T.name == "light" else T.seq[2:]
    fig = _map_fig(T, [piv.loc[2025, d] for d in DIVS], lo, hi, colors,
                   "%{customdata}: <b>%{z:.0f}</b> reported crimes per 100,000 people<extra></extra>",
                   dict(title=dict(text="per 100k", side="top", font=dict(color=T.ink2, size=11))))
    opts = []
    years = list(piv.index)
    for y in years:
        vals = piv.loc[y]
        txt, tc = _labels(T, vals, "{:.0f}", colors, lo, hi)
        opts.append({"label": f"{y}" + (" (Jan–Aug, annualised)" if y == 2026 else ""),
                     "restyle": [[{"z": [[vals[d] for d in DIVS]]}, [0]],
                                 [{"text": [txt], "textfont.color": [tc]}, [1]]],
                     "relayout": {}})
    ctl = {"label": "Year", "options": opts, "default": years.index(2025)}
    apply_default(fig, ctl)
    data = div[["year", "division", "population", A.REPORTED, col]].rename(
        columns={col: "reported_per_100k_per_year"})
    return Chart("plotly", fig, [ctl], data=data, height=560)


def map_change(T, R):
    m = R["m"]
    w = m[m.division != "-"]
    opts = {"Violent crime (murder + dacoity + robbery + kidnapping)": A.VIOLENT,
            "Murder": ["Murder"], "Dacoity": ["Dacoity"], "Robbery": ["Robbery"],
            "Kidnapping": ["Kidnapping"], "Arms Act": ["Arms Act"], "Narcotics": ["Narcotics"]}
    pre, post = A.window_means(w, A.HEADS, "division")
    chg = {k: ((post[v].sum(axis=1) / pre[v].sum(axis=1)) - 1) * 100 for k, v in opts.items()}
    M = float(np.ceil(max(np.abs(c).max() for c in chg.values()) / 10) * 10)
    first = chg[list(opts)[0]]
    fig = _map_fig(T, [first[d] for d in DIVS], -M, M, T.div,
                   "%{customdata}: <b>%{z:+.0f}%</b><extra></extra>",
                   dict(ticksuffix="%", title=dict(text="change", side="top",
                                                   font=dict(color=T.ink2, size=11))), zmid=0)
    o = []
    for k in opts:
        Mk = float(np.ceil(np.abs(chg[k]).max() / 10) * 10)
        txt, tc = _labels(T, chg[k], "{:+.0f}%", T.div, -Mk, Mk)
        o.append({"label": k, "restyle": [[{"z": [[chg[k][d] for d in DIVS]], "zmin": [-Mk],
                                            "zmax": [Mk]}, [0]],
                                          [{"text": [txt], "textfont.color": [tc]}, [1]]],
                  "relayout": {}})
    ctl = {"label": "Crime", "options": o, "default": 0}
    apply_default(fig, ctl)
    data = pd.DataFrame({k: v for k, v in chg.items()}).rename_axis("division").reset_index()
    return Chart("plotly", fig, [ctl], data=data, height=560)


def dumbbell(T, R):
    m = R["m"]
    opts = {"Violent crime (murder + dacoity + robbery + kidnapping)": A.VIOLENT,
            "Murder": ["Murder"], "Dacoity": ["Dacoity"], "Robbery": ["Robbery"],
            "Kidnapping": ["Kidnapping"]}
    pre, post = A.window_means(m, A.HEADS, "unit")
    fig = go.Figure()
    groups, layouts, rows = [], [], []
    for k, cols in opts.items():
        d = pd.DataFrame({"pre": pre[cols].sum(axis=1), "post": post[cols].sum(axis=1)})
        d["chg"] = (d.post / d.pre - 1) * 100
        d = d.sort_values("post")
        i0 = len(fig.data)
        for up, c in [(True, role(T, "orange")), (False, role(T, "blue"))]:
            sub = d[(d.post > d.pre) == up]
            xs, ys = [], []
            for u, r in sub.iterrows():
                xs += [r.pre, r.post, None]
                ys += [u, u, None]
            fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=c, width=3.5),
                            hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=d.pre, y=d.index, mode="markers", name="Aug 2022 – Jul 2024",
                        legendgroup="pre", showlegend=(i0 == 0),
                        marker=dict(size=12, color=T.context, line=dict(color=T.surface, width=2)),
                        hovertemplate="%{y}<br>before: <b>%{x:.1f}</b> per month<extra></extra>")
        fig.add_scatter(x=d.post, y=d.index, mode="markers+text", name="Sep 2024 – Aug 2026",
                        legendgroup="post", showlegend=(i0 == 0),
                        marker=dict(size=12, color=role(T, "orange"),
                                    line=dict(color=T.surface, width=2)),
                        text=[f"  {c:+.0f}%" if np.isfinite(c) else "" for c in d.chg],
                        textposition="middle right", textfont=dict(size=12, color=T.ink),
                        customdata=d.chg, hovertemplate="%{y}<br>after: <b>%{x:.1f}</b> per month"
                                                        " (%{customdata:+.0f}%)<extra></extra>")
        groups.append(list(range(i0, len(fig.data))))
        layouts.append({"yaxis.categoryarray": list(d.index)})
        rows.append(d.assign(crime=k).reset_index())
    fig.update_layout(plotly_layout(
        T, margin=dict(l=130, r=40, t=40, b=48),
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", font=dict(color=T.ink2)),
        xaxis=axis(T, type="log", showgrid=True, title="mean cases per month (log scale)",
                   tickvals=[0.5, 1, 2, 5, 10, 20, 50, 100, 200],
                   ticktext=["0.5", "1", "2", "5", "10", "20", "50", "100", "200"]),
        yaxis=axis(T, showgrid=False, categoryorder="array")))
    ctl = control("Crime", list(opts), groups, len(fig.data), layouts)
    apply_default(fig, ctl)
    return Chart("plotly", fig, [ctl], data=pd.concat(rows), height=640)


UNIT_ORDER = ["DMP", "CMP", "GMP", "KMP", "RMP", "SMP", "BMP", "RPMP", "Dhaka Range",
              "Chittagong Range", "Mymensingh Range", "Sylhet Range", "Khulna Range",
              "Barishal Range", "Rajshahi Range", "Rangpur Range", "Railway Range"]


def unit_heatmap(T, R):
    m = R["m"]
    focus = ["Kidnapping", "Dacoity", "Robbery", "Arms Act", "Burglary", "Murder",
             "Woman & Child Repression", "Theft", "Other Cases", "Narcotics"]
    pre, post = A.window_means(m, focus, "unit")
    chg = ((post + 0.5) / (pre + 0.5) - 1) * 100
    chg, pre, post = chg.loc[UNIT_ORDER], pre.loc[UNIT_ORDER], post.loc[UNIT_ORDER]
    z = chg.clip(-100, 200)
    # piecewise scale: -100 -> blue end, 0 -> grey, +200 -> red end
    cs = [[0, T.div[0]], [1 / 9, T.div[1]], [2 / 9, T.div[2]], [1 / 3, T.div[3]],
          [5 / 9, T.div[4]], [7 / 9, T.div[5]], [1, T.div[6]]]
    custom = np.dstack([pre.values, post.values, chg.values])
    fig = go.Figure(go.Heatmap(
        z=z.values, x=[lab(h).replace("Woman & child repression", "Woman & child<br>repression")
                       for h in focus], y=UNIT_ORDER, zmin=-100, zmax=200, colorscale=cs,
        text=chg.round(0).astype(int).map(lambda v: f"{v:+d}%").values, texttemplate="%{text}",
        textfont=dict(size=11), customdata=custom, xgap=2, ygap=2,
        hovertemplate="%{y} · %{x}<br>before <b>%{customdata[0]:.1f}</b>/month → after "
                      "<b>%{customdata[1]:.1f}</b>/month<br>change <b>%{customdata[2]:+.0f}%</b>"
                      "<extra></extra>",
        colorbar=dict(thickness=10, outlinewidth=0, len=0.7, ticksuffix="%",
                      tickvals=[-100, -50, 0, 50, 100, 150, 200], tickfont=dict(color=T.ink2))))
    for yv in (7.5, 15.5):
        fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=yv, y1=yv,
                      line=dict(color=T.ink, width=1.5))
    fig.update_layout(plotly_layout(
        T, margin=dict(l=130, r=16, t=60, b=16),
        xaxis=axis(T, side="top", showgrid=False, tickfont=dict(size=11, color=T.ink2)),
        yaxis=axis(T, autorange="reversed", showgrid=False)))
    data = chg.round(1).rename_axis("unit").reset_index()
    return Chart("plotly", fig, data=data, height=640)


def bump(T, R):
    m = R["m"]
    w = m[m.unit != "Railway Range"]
    months = w.groupby("year").date.nunique()
    yr = w.groupby(["year", "unit"])[A.REPORTED].sum().reset_index()
    yr["per_year"] = (yr[A.REPORTED] * 12 / yr.year.map(months)).round(0)
    yr["rank"] = yr.groupby("year").per_year.rank(ascending=False, method="first").astype(int)
    first, last = yr.year.min(), yr.year.max()
    move = (yr[yr.year == first].set_index("unit")["rank"] - yr[yr.year == last].set_index("unit")["rank"])
    focus = ["DMP"] + [u for u in move.abs().sort_values(ascending=False).index if u != "DMP"][:3]
    pal = dict(zip(focus, [role(T, "blue"), role(T, "orange"), role(T, "aqua"), role(T, "violet")]))
    yr["focus"] = yr.unit.where(yr.unit.isin(focus), "Other units")
    yr["sw"] = np.where(yr.focus == "Other units", 1.4, 3.0)
    yr["year_s"] = yr.year.astype(str) + np.where(yr.year == last, "*", "")
    order = [str(y) for y in sorted(yr.year.unique())]
    order[-1] += "*"
    dom, rng = focus + ["Other units"], [pal[u] for u in focus] + [T.context]
    hover = alt.selection_point(fields=["unit"], on="pointerover", clear="pointerout", empty=False)
    x = alt.X("year_s:O", sort=order, title=None, scale=alt.Scale(padding=0.6),
              axis=alt.Axis(labelAngle=0, domain=False, ticks=False, orient="top"))
    y = alt.Y("rank:O", title=None, axis=None)
    base = alt.Chart(yr).encode(x=x, y=y, detail="unit:N",
                                color=alt.condition(hover, alt.value(T.ink),
                                                    alt.Color("focus:N", scale=alt.Scale(domain=dom, range=rng),
                                                              legend=None)))
    lines = base.mark_line(interpolate="monotone").encode(
        strokeWidth=alt.condition(hover, alt.value(4.5), alt.StrokeWidth("sw:Q", scale=None, legend=None)),
        opacity=alt.condition(alt.datum.focus == "Other units", alt.value(0.7), alt.value(1)))
    pts = base.mark_circle(size=110, opacity=1, stroke=T.surface, strokeWidth=2).encode(
        tooltip=[alt.Tooltip("unit:N", title="Unit"), alt.Tooltip("year:O", title="Year"),
                 alt.Tooltip("per_year:Q", format=",", title="Reported crimes per year"),
                 alt.Tooltip("rank:O", title="Rank")]).add_params(hover)

    def labels(year, align, dx):
        sub = yr[yr.year == year]
        out = []   # fontWeight is not an encoding channel: one layer per weight
        for is_focus, weight, col in [(True, 700, T.ink), (False, 400, T.ink2)]:
            part = sub[(sub.focus != "Other units") == is_focus]
            out.append(alt.Chart(part).mark_text(align=align, dx=dx, fontSize=12, fontWeight=weight,
                                                 color=col).encode(
                x=alt.X("year_s:O", sort=order), y="rank:O", text="unit:N"))
        return out[0] + out[1]
    chart = (lines + pts + labels(last, "left", 12) + labels(first, "right", -12)).properties(
        width="container", height=470)
    return Chart("vega", chart, data=yr, height=520, fit="single")


def _place(points, xr, yr, w=880, h=540):
    """Greedy label placement: pixel offsets that avoid earlier labels and points."""
    sx, sy = w / (xr[1] - xr[0]), h / (yr[1] - yr[0])
    px = [((x - xr[0]) * sx, (yr[1] - y) * sy) for _, x, y in points]
    cands = [(0, -20), (0, 20), (34, -14), (-34, -14), (34, 14), (-34, 14), (0, -38), (0, 38),
             (55, 0), (-55, 0), (50, -30), (-50, -30), (50, 30), (-50, 30)]
    placed, out = [], []

    def ov(a, b):
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    for (name, _, _), (x0, y0) in zip(points, px):
        wl, hl = 7.2 * len(name) + 6, 16
        best = None
        for ax, ay in cands:
            cx, cy = x0 + ax, y0 + ay
            box = (cx - wl / 2, cy - hl / 2, cx + wl / 2, cy + hl / 2)
            cost = sum(ov(box, b) for b in placed) + sum(
                ov(box, (p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8)) * 3 for p in px)
            cost += 0.02 * (abs(ax) + abs(ay))
            if box[0] < 0 or box[2] > w or box[1] < 0 or box[3] > h:
                cost += 1e5
            if best is None or cost < best[0]:
                best = (cost, ax, ay, box)
        placed.append(best[3])
        out.append((best[1], best[2]))
    return out


def clusters(T, R):
    cl, ld, meta = R["cl"], R["load"], R["meta"]
    cols = {"Metro & port belt": role(T, "blue"), "Northern agrarian ranges": role(T, "green"),
            "Dhaka–Barishal ring": role(T, "orange")}
    span = max(np.abs(cl[["pc1", "pc2"]]).max().max(), 0.1)
    scl = span / np.abs(ld).max().max() * 0.85
    xr = [cl.pc1.min() - 0.35 * span, cl.pc1.max() + 0.35 * span]
    yr = [cl.pc2.min() - 0.3 * span, cl.pc2.max() + 0.3 * span]
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=T.axis, width=0.8))
    fig.add_vline(x=0, line=dict(color=T.axis, width=0.8))
    top = (ld.pc1 ** 2 + ld.pc2 ** 2).sort_values(ascending=False).index[:8]
    placed = []
    for h in top:
        x, y = ld.loc[h, "pc1"] * scl, ld.loc[h, "pc2"] * scl
        fig.add_annotation(x=x, y=y, ax=0, ay=0, axref="x", ayref="y", showarrow=True, text="",
                           arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor=T.muted)
        lx, ly = x * 1.14, y * 1.14
        # label only arrows long enough, and never on top of another label
        if np.hypot(x, y) > 0.3 * span and all(np.hypot(lx - a, (ly - b) * 2.2) > 0.45 * span
                                               for a, b in placed):
            placed.append((lx, ly))
            fig.add_annotation(x=lx, y=ly, text=f"<i>{lab(h)}</i>", showarrow=False,
                               font=dict(size=11, color=T.ink2))
    share = cl[A.HEADS]
    base = share.mean()
    for name in cols:
        sub = cl[cl.cluster_name == name]
        over = [", ".join(lab(h) for h in (share.loc[u] / base).sort_values(ascending=False).index[:3])
                for u in sub.index]
        fig.add_scatter(x=sub.pc1, y=sub.pc2, mode="markers", name=name,
                        marker=dict(size=16, color=cols[name], line=dict(color=T.surface, width=2)),
                        customdata=np.stack([sub.index, over], axis=1),
                        hovertemplate="<b>%{customdata[0]}</b><br>" + name +
                                      "<br>Most over-represented: %{customdata[1]}<extra></extra>")
    pts = [(u, r.pc1, r.pc2) for u, r in cl.iterrows()]
    for (u, x, y), (ax, ay) in zip(pts, _place(pts, xr, yr)):
        fig.add_annotation(x=x, y=y, ax=ax, ay=ay, text=f"<b>{u}</b>", showarrow=True, arrowhead=0,
                           arrowwidth=0.7, arrowcolor=T.axis, standoff=8,
                           font=dict(size=12, color=T.ink))
    ev = meta["explained"]
    fig.update_layout(plotly_layout(
        T, margin=dict(l=56, r=16, t=40, b=48),
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", title=None,
                    font=dict(color=T.ink2, size=12)),
        xaxis=axis(T, range=xr, showgrid=False, zeroline=False,
                   title=f"PC1 ({ev[0] * 100:.0f}% of variance)"),
        yaxis=axis(T, range=yr, showgrid=False, zeroline=False,
                   title=f"PC2 ({ev[1] * 100:.0f}% of variance)")))
    data = cl.rename_axis("unit").reset_index()
    return Chart("plotly", fig, data=data, height=620)


def radar(T, R):
    cl = R["cl"]
    share = cl[A.HEADS]
    base = share.mean()
    heads = ["Narcotics", "Smuggling", "Arms Act", "Robbery", "Burglary", "Theft", "Dacoity",
             "Kidnapping", "Murder", "Woman & Child Repression", "Other Cases", "Speedy Trial",
             "Police Assault"]
    cols = {"Metro & port belt": role(T, "blue"), "Northern agrarian ranges": role(T, "green"),
            "Dhaka–Barishal ring": role(T, "orange")}
    fig = go.Figure()
    rows = []
    for name, c in cols.items():
        idx = (share[cl.cluster_name == name].mean() / base * 100)[heads]
        th = [lab(h) for h in heads]
        fig.add_scatterpolar(r=list(idx) + [idx.iloc[0]], theta=th + [th[0]], name=name,
                             line=dict(color=c, width=2.5), fill="toself", fillcolor=rgba(c, 0.12),
                             hovertemplate="%{theta}: <b>%{r:.0f}</b><extra>" + name + "</extra>")
        rows.append(idx.rename("index").reset_index().assign(cluster=name))
    fig.update_layout(plotly_layout(
        T, margin=dict(l=90, r=90, t=40, b=40),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1.04, yanchor="bottom",
                    font=dict(color=T.ink2)),
        polar=dict(bgcolor=T.surface,
                   radialaxis=dict(range=[0, 260], tickvals=[50, 100, 150, 200, 250], gridcolor=T.grid,
                                   linecolor=T.axis, tickfont=dict(size=10, color=T.muted), angle=90,
                                   tickangle=90),
                   angularaxis=dict(gridcolor=T.grid, linecolor=T.axis,
                                    tickfont=dict(size=12, color=T.ink2)))))
    return Chart("plotly", fig, data=pd.concat(rows), height=620)


def race(T, R):
    m = R["m"]
    yr = m.groupby(["year", "unit"])[A.REPORTED].sum().reset_index()
    months = m.groupby("year").date.nunique()
    yr["annualised"] = yr[A.REPORTED] * 12 / yr.year.map(months)
    color = {u: role(T, "blue") if "Range" not in u else role(T, "orange") for u in A.UNITS}
    color["Railway Range"] = T.context
    years = sorted(yr.year.unique())
    xmax = yr.annualised.max() * 1.15
    frames = []
    for y in years:
        d = yr[yr.year == y].sort_values("annualised")
        frames.append(go.Frame(name=str(y), data=[go.Bar(
            x=d.annualised, y=d.unit, orientation="h",
            marker=dict(color=[color[u] for u in d.unit], cornerradius=4),
            text=[f"{v:,.0f}" for v in d.annualised], textposition="outside",
            textfont=dict(color=T.ink, size=11), cliponaxis=False,
            hovertemplate="%{y}: <b>%{x:,.0f}</b> reported crimes" +
                          (" (annualised)" if months[y] < 12 else "") + "<extra></extra>")],
            layout=go.Layout(annotations=[dict(
                x=0.98, y=0.06, xref="paper", yref="paper", text=f"<b>{y}</b>" +
                ("<br><span style='font-size:13px'>Jan–Aug, annualised</span>" if months[y] < 12 else ""),
                showarrow=False, xanchor="right", font=dict(size=44, color=T.context))])))
    fig = go.Figure(data=frames[0].data, frames=frames, layout=frames[0].layout)
    fig.update_layout(plotly_layout(
        T, margin=dict(l=130, r=24, t=16, b=90),
        xaxis=axis(T, range=[0, xmax], showgrid=True, title="reported crimes per year"),
        yaxis=axis(T, showgrid=False, tickfont=dict(size=11, color=T.ink2)),
        updatemenus=[dict(type="buttons", direction="left", x=0, y=-0.13, xanchor="left", yanchor="top",
                          showactive=False, **dropdown_style(T), buttons=[
            dict(label="▶ Play", method="animate",
                 args=[None, dict(frame=dict(duration=1100, redraw=True), fromcurrent=True,
                                  transition=dict(duration=450))]),
            dict(label="❚❚ Pause", method="animate",
                 args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])],
        sliders=[dict(x=0.24, y=-0.11, len=0.76, yanchor="top", currentvalue=dict(visible=False),
                      bgcolor=T.grid, bordercolor=T.axis, activebgcolor=role(T, "blue"),
                      font=dict(color=T.ink2), tickcolor=T.axis,
                      steps=[dict(label=str(y), method="animate",
                                  args=[[str(y)], dict(mode="immediate",
                                                       frame=dict(duration=300, redraw=True),
                                                       transition=dict(duration=300))])
                             for y in years])]))
    return Chart("plotly", fig, data=yr, height=640)


# ===========================================================================
# Chapter 6 - a slow return?
# ===========================================================================
def brush(T, R):
    nat = R["nat"]
    dom = ["Total Cases", A.REPORTED, "Recovery Total"]
    names = {"Total Cases": "All recorded cases", A.REPORTED: "Reported crime",
             "Recovery Total": "Recovery cases"}
    d = nat[dom].rename(columns=names).reset_index().melt("date", var_name="series", value_name="cases")
    d["date"] = d.date.dt.strftime("%Y-%m-%d")
    rng = [role(T, "violet"), role(T, "orange"), role(T, "aqua")]
    sel = alt.selection_interval(encodings=["x"], value={"x": [alt.DateTime(year=2023, month=6, date=1),
                                                               alt.DateTime(year=2026, month=8, date=31)]})
    color = alt.Color("series:N", scale=alt.Scale(domain=list(names.values()), range=rng),
                      legend=alt.Legend(title=None, orient="top"))
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False,
                                clear="pointerout")
    xs = alt.X("date:T", scale=alt.Scale(domain=sel), title=None, axis=alt.Axis(format="%b %Y"))
    line = alt.Chart(d).mark_line(strokeWidth=2.2, interpolate="monotone").encode(
        x=xs, y=alt.Y("cases:Q", title="cases per month", axis=alt.Axis(format="~s")), color=color)
    rule = alt.Chart(d).transform_pivot("series", value="cases", groupby=["date"]).mark_rule(
        color=T.ink2).encode(
        x=xs, opacity=alt.condition(hover, alt.value(0.8), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", format="%B %Y", title="Month")] +
                [alt.Tooltip(f"{n}:Q", format=",") for n in names.values()]).add_params(hover)
    upper = (line + rule).properties(width=760, height=300)
    lower = alt.Chart(d).mark_area(opacity=0.45, interpolate="monotone").encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y("cases:Q", stack=None, title=None, axis=alt.Axis(labels=False, ticks=False, grid=False)),
        color=alt.Color("series:N", scale=alt.Scale(domain=list(names.values()), range=rng), legend=None)
    ).add_params(sel).properties(width=760, height=70)
    chart = alt.vconcat(upper, lower, spacing=10)
    return Chart("vega", chart, data=d, height=470, fit="vconcat")


def forecast(T, R):
    fc, perf, nat = R["fc"], R["perf"], R["nat"]
    blue, orange = role(T, "blue"), role(T, "orange")
    fig = go.Figure()
    groups, layouts = [], []
    for k, s in enumerate(A.FORECAST):
        f = fc[(fc.series == s) & fc["mean"].notna()]
        b = fc[(fc.series == s) & fc["backtest"].notna()]
        first = k == 0
        i0 = len(fig.data)
        fig.add_scatter(x=nat.index, y=nat[s], name="Observed", legendgroup="obs", showlegend=first,
                        line=dict(color=T.ink2, width=1.6),
                        hovertemplate="<b>%{y:,}</b> observed<extra></extra>")
        for lo, hi, a, nm in [("lo95", "hi95", 0.14, "95% interval"), ("lo80", "hi80", 0.24, "80% interval")]:
            fig.add_scatter(x=f.date, y=f[lo], mode="lines", line=dict(width=0), hoverinfo="skip",
                            showlegend=False,
                            legendgroup=nm)
            fig.add_scatter(x=f.date, y=f[hi], mode="lines", line=dict(width=0), fill="tonexty",
                            fillcolor=rgba(blue, a), name=nm, legendgroup=nm, showlegend=first,
                            customdata=f[lo], hovertemplate=f"{nm}: %{{customdata:,.0f}} – %{{y:,.0f}}"
                                                            "<extra></extra>")
        fig.add_scatter(x=f.date, y=f["mean"], mode="lines", name="Forecast", legendgroup="fc",
                        showlegend=first,
                        line=dict(color=blue, width=2.6),
                        hovertemplate="<b>%{y:,.0f}</b> forecast<extra></extra>")
        fig.add_scatter(x=b.date, y=b.backtest, name="1-step backtest", legendgroup="bt",
                        showlegend=first, mode="lines+markers", line=dict(color=orange, width=1.6),
                        marker=dict(size=6, color=orange, line=dict(color=T.surface, width=1)),
                        hovertemplate="<b>%{y:,.0f}</b> backtest forecast<extra></extra>")
        groups.append(list(range(i0, len(fig.data))))
        r = perf.loc[s]
        sea = "" if r.seasonal[:3] == (0, 0, 0) else f"{tuple(r.seasonal[:3])}₁₂"
        hist = nat.loc["2022-01-31":, s]
        layouts.append({"annotations[0].text":
                        f"<b>{lab(s)}</b> · ARIMA{tuple(r.order)}{sea} + Fourier terms<br>"
                        f"Backtest MAPE {r.mape:.1f}% (seasonal naive {r.mape_naive:.1f}%)<br>"
                        f"Next 12 months: {r.next12:,.0f} (last 12: {r.last12:,.0f})",
                        "yaxis.range": [max(0, min(hist.min(), f.lo95.min()) * 0.7),
                                        max(hist.max(), f.hi95.max()) * 1.18]})
    fig.add_annotation(x=0.01, y=0.98, xref="paper", yref="paper", text="", showarrow=False,
                       xanchor="left", yanchor="top", align="left", bgcolor=T.surface,
                       bordercolor=T.grid, borderpad=6, font=dict(size=12, color=T.ink))
    fig.add_vline(x=pd.Timestamp("2024-08-05").timestamp() * 1000, line=dict(color=T.muted, width=1))
    fig.update_layout(plotly_layout(
        T, hovermode="x unified", margin=dict(l=56, r=16, t=40, b=40),
        xaxis=axis(T, range=[pd.Timestamp("2022-01-01"), fc.date.max() + pd.Timedelta(days=20)],
                   hoverformat="%B %Y"),
        yaxis=axis(T, showgrid=True, tickformat="~s", title="cases per month")))
    ctl = control("Series", [lab(s) for s in A.FORECAST], groups, len(fig.data), layouts)
    apply_default(fig, ctl)
    return Chart("plotly", fig, [ctl], data=fc, height=520)


BUILDERS = {
    "sunburst": sunburst, "hero": hero, "calendar": calendar, "seasonal": seasonal, "stl": stl,
    "correlation": correlation, "small_multiples": small_multiples, "forest": forest, "its": its,
    "anomalies": anomalies, "murder_backlog": murder_backlog, "ridgeline": ridgeline,
    "family_share": family_share, "yoy": yoy, "map_rates": map_rates, "map_change": map_change,
    "dumbbell": dumbbell, "unit_heatmap": unit_heatmap, "bump": bump, "clusters": clusters,
    "radar": radar, "race": race, "brush": brush, "forecast": forecast,
}
