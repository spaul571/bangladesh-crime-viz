"""Design tokens for the website, in a light and a dark variant.

The light values are the ones used in the printed report (src/viz_style.py).
The dark values are the same hues stepped for a dark surface. Every chart is
built twice, once per theme, so colours never have to be guessed at runtime.
"""
from types import SimpleNamespace

FONT = '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif'

# Sequential blue ramp, step 100 -> 700.
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
       "#0d366b"]

LIGHT = SimpleNamespace(
    name="light",
    surface="#fcfcfb", page="#f9f9f7",
    ink="#0b0b0b", ink2="#52514e", muted="#898781",
    grid="#e1e0d9", axis="#c3c2b7", context="#c9c8c1",
    # categorical slots: blue, orange, aqua, yellow, magenta, green, violet, red
    cat=["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
         "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    seq=SEQ,                       # low -> high
    div=["#104281", "#2a78d6", "#86b6ef", "#f0efec", "#f2a3a2", "#e34948", "#a51d1d"],
    shade="rgba(225,224,217,0.75)",   # COVID band
    on_dark="#ffffff", on_light="#0b0b0b",
)

DARK = SimpleNamespace(
    name="dark",
    surface="#1a1a19", page="#0d0d0d",
    ink="#ffffff", ink2="#c3c2b7", muted="#898781",
    grid="#2c2c2a", axis="#383835", context="#55544f",
    cat=["#3987e5", "#d95926", "#199e70", "#c98500",
         "#d55181", "#008300", "#9085e9", "#e66767"],
    seq=SEQ[::-1],                 # on a dark surface, low values recede into it
    div=["#b7d3f6", "#5598e7", "#1c5cab", "#383835", "#a83a39", "#e66767", "#f6c1c0"],
    shade="rgba(56,56,53,0.85)",
    on_dark="#ffffff", on_light="#0b0b0b",
)

THEMES = [LIGHT, DARK]


def role(T, name):
    """Named categorical slot."""
    return T.cat[["blue", "orange", "aqua", "yellow", "magenta", "green",
                  "violet", "red"].index(name)]


def rgba(hex_, a):
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _lum(hex_):
    h = hex_.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def text_on(hex_):
    """Ink that reads best on a filled cell of colour hex_."""
    L = _lum(hex_)
    return "#ffffff" if (1.05 / (L + 0.05)) > ((L + 0.05) / 0.05) else "#0b0b0b"


def ramp_at(colors, t):
    """Colour at position t (0..1) of a piecewise-linear ramp."""
    t = min(max(float(t), 0.0), 1.0)
    pos = t * (len(colors) - 1)
    i = min(int(pos), len(colors) - 2)
    f = pos - i
    a, b = colors[i].lstrip("#"), colors[i + 1].lstrip("#")
    mix = [round(int(a[k:k + 2], 16) * (1 - f) + int(b[k:k + 2], 16) * f) for k in (0, 2, 4)]
    return "#" + "".join(f"{v:02x}" for v in mix)


def scale(colors):
    return [[i / (len(colors) - 1), c] for i, c in enumerate(colors)]


def plotly_layout(T, **kw):
    """Base layout shared by every Plotly chart (titles live in the HTML)."""
    base = dict(
        font=dict(family=FONT, size=13, color=T.ink2),
        paper_bgcolor=T.surface, plot_bgcolor=T.surface,
        colorway=T.cat,
        margin=dict(l=56, r=24, t=28, b=44),
        hoverlabel=dict(bgcolor=T.surface, bordercolor=T.axis,
                        font=dict(family=FONT, size=13, color=T.ink)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=12, color=T.ink2),
                    orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom"),
        xaxis=dict(gridcolor=T.grid, linecolor=T.axis, zeroline=False, ticks="",
                   showgrid=False, tickfont=dict(color=T.ink2)),
        yaxis=dict(gridcolor=T.grid, linecolor=T.axis, zeroline=False, ticks="",
                   showline=False, tickfont=dict(color=T.ink2)),
        hovermode="closest",
        dragmode="zoom",
        modebar=dict(bgcolor="rgba(0,0,0,0)", color=T.muted, activecolor=T.ink),
    )
    base.update(kw)
    return base


def axis(T, **kw):
    a = dict(gridcolor=T.grid, linecolor=T.axis, zeroline=False, ticks="", showgrid=False,
             tickfont=dict(color=T.ink2), title=dict(font=dict(color=T.ink2)))
    a.update(kw)
    return a


def vega_config(T):
    """Vega-Lite config: the Altair counterpart of plotly_layout."""
    return {
        "background": T.surface,
        "font": FONT,
        "padding": {"left": 6, "right": 6, "top": 8, "bottom": 6},
        "view": {"stroke": None},
        "axis": {"labelColor": T.ink2, "titleColor": T.ink2, "gridColor": T.grid,
                 "domainColor": T.axis, "tickColor": T.axis, "labelFont": FONT,
                 "titleFont": FONT, "titleFontWeight": 500, "labelFontSize": 12,
                 "titleFontSize": 12},
        "legend": {"labelColor": T.ink2, "titleColor": T.ink2, "labelFont": FONT,
                   "titleFont": FONT, "labelFontSize": 12},
        "header": {"labelFont": FONT, "titleFont": FONT, "labelColor": T.ink,
                   "labelFontSize": 12},
        "text": {"font": FONT, "color": T.ink},
        "range": {"category": T.cat, "ramp": T.seq[1:], "diverging": T.div},
        "tooltip": {},
    }
