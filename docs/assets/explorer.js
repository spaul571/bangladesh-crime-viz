/* Overview at the top of the page: the web version of the Dash dashboard
 * (dashboard/app.py).
 *
 * One filter row (period, police units, crime heads) scopes the totals and the
 * eight charts below it. Everything is computed in the browser from
 * data/explorer.json, which build_site.py writes from the Excel dataset.
 * A crime head keeps its colour whatever the selection.
 */
(function () {
  "use strict";
  const root = document.documentElement;
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const theme = () => root.dataset.theme || (mq.matches ? "dark" : "light");
  const FONT = '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif';

  const T = {
    light: { surface: "#fcfcfb", ink: "#0b0b0b", ink2: "#52514e", muted: "#898781", grid: "#e1e0d9",
      axis: "#c3c2b7", context: "#a8a79f", faint: "#9ec5f4",
      cat: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
      seq: ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
        "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"],
      fam: { "Recovery (police-initiated)": "#1baf7a", "Other cases": "#c9c8c1",
        "Violence against person": "#eb6834", "Property": "#2a78d6", "Violent property": "#e34948",
        "Public order": "#4a3aa7" } },
    dark: { surface: "#1a1a19", ink: "#ffffff", ink2: "#c3c2b7", muted: "#898781", grid: "#2c2c2a",
      axis: "#383835", context: "#6b6a65", faint: "#1c5cab",
      cat: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
      seq: ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7",
        "#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb"],
      fam: { "Recovery (police-initiated)": "#199e70", "Other cases": "#55544f",
        "Violence against person": "#d95926", "Property": "#3987e5", "Violent property": "#e66767",
        "Public order": "#9085e9" } },
  };
  const FAMILIES = ["Recovery (police-initiated)", "Other cases", "Violence against person", "Property",
    "Violent property", "Public order"];
  // Eight focus heads own the categorical slots; the rest are grey with distinct dashes.
  const FOCUS = ["Murder", "Robbery", "Dacoity", "Kidnapping", "Woman & Child Repression",
    "Narcotics", "Theft", "Arms Act"];
  const DASHES = ["dot", "dash", "longdash", "dashdot", "longdashdot", "5px,2px", "2px,6px"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const BREAK = "2024-08-05";

  let D = null;
  const S = { from: 0, to: 0, units: new Set(), heads: new Set(["Murder", "Robbery", "Dacoity", "Kidnapping"]) };
  const $ = (id) => document.getElementById(id);
  const fmt = (v) => Math.round(v).toLocaleString("en-US");
  // ink that reads best on a cell of the sequential ramp at position t (0..1)
  function textOn(seq, t) {
    const h = seq[Math.round(Math.min(Math.max(t, 0), 1) * (seq.length - 1))].slice(1);
    const lin = [0, 2, 4].map((k) => { const c = parseInt(h.slice(k, k + 2), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); });
    const L = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
    return 1.05 / (L + 0.05) > (L + 0.05) / 0.05 ? "#ffffff" : "#0b0b0b";
  }
  const mlabel = (iso) => { const [y, m] = iso.split("-"); return MONTHS[+m - 1] + " " + y; };

  function headStyle(h) {
    const P = T[theme()];
    const i = FOCUS.indexOf(h);
    if (i >= 0) return { color: P.cat[i], dash: "solid" };
    const others = D.heads.filter((x) => !FOCUS.includes(x));
    return { color: P.context, dash: DASHES[others.indexOf(h) % DASHES.length] };
  }

  function layout(extra) {
    const P = T[theme()];
    const ax = { gridcolor: P.grid, linecolor: P.axis, zeroline: false, ticks: "", tickfont: { color: P.ink2 } };
    const base = {
      font: { family: FONT, size: 12.5, color: P.ink2 }, paper_bgcolor: P.surface, plot_bgcolor: P.surface,
      margin: { l: 52, r: 16, t: 12, b: 36 }, autosize: true,
      hoverlabel: { bgcolor: P.surface, bordercolor: P.axis, font: { family: FONT, color: P.ink } },
      legend: { orientation: "h", x: 0, y: -0.14, font: { color: P.ink2 } },
      modebar: { bgcolor: "rgba(0,0,0,0)", color: P.muted, activecolor: P.ink },
      xaxis: Object.assign({}, ax, { showgrid: false }), yaxis: Object.assign({}, ax, { showgrid: true }),
    };
    for (const k in extra) {
      base[k] = (k === "xaxis" || k === "yaxis") ? Object.assign(base[k], extra[k]) : extra[k];
    }
    return base;
  }
  const CFG = { responsive: true, displaylogo: false, displayModeBar: "hover",
    modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"] };

  // the 5 August 2024 marker, shown when the period includes it
  function breakMarker(P) {
    if (!(BREAK > D.months[S.from].slice(0, 8) + "01" && BREAK <= D.months[S.to])) return { shapes: [], annotations: [] };
    return {
      shapes: [{ type: "line", x0: BREAK, x1: BREAK, yref: "paper", y0: 0, y1: 1, line: { color: P.ink2, width: 1 } }],
      annotations: [{ x: BREAK, y: 1, yref: "paper", text: "5 Aug 2024<br>government falls", showarrow: false,
        xanchor: "left", yanchor: "top", align: "left", xshift: 4, font: { size: 10.5, color: P.ink2 } }],
    };
  }

  // ---------------------------------------------------------------- data
  const col = (name) => D.cols.indexOf(name);
  function unitIdx() {
    return S.units.size ? D.units.map((u, i) => (S.units.has(u) ? i : -1)).filter((i) => i >= 0)
      : D.units.map((_, i) => i);
  }
  function monthSum(mi, units, c) {
    let s = 0;
    for (const u of units) s += D.values[mi][u][c];
    return s;
  }

  // ---------------------------------------------------------------- controls
  function buildControls() {
    const from = $("from"), to = $("to");
    D.months.forEach((m, i) => {
      from.add(new Option(mlabel(m), i));
      to.add(new Option(mlabel(m), i));
    });
    S.to = D.months.length - 1;
    from.value = 0; to.value = S.to;
    from.addEventListener("change", () => { S.from = +from.value; if (S.from > S.to) { S.to = S.from; to.value = S.to; } update(); });
    to.addEventListener("change", () => { S.to = +to.value; if (S.to < S.from) { S.from = S.to; from.value = S.from; } update(); });

    // period buttons: all years, each year, the last 12 months
    const years = [...new Set(D.months.map((m) => m.slice(0, 4)))];
    const n = D.months.length;
    const presets = [["All years", 0, n - 1]];
    years.forEach((y) => {
      const idx = D.months.map((m, i) => (m.startsWith(y) ? i : -1)).filter((i) => i >= 0);
      presets.push([y, idx[0], idx[idx.length - 1]]);
    });
    presets.push(["Last 12 months", n - 12, n - 1]);
    const box = $("presets");
    presets.forEach(([label, a, b], k) => {
      if (k === 1 || k === presets.length - 1) {
        const sep = document.createElement("span");
        sep.className = "sep";
        box.append(sep);
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      btn.dataset.a = a; btn.dataset.b = b;
      btn.addEventListener("click", () => { S.from = a; S.to = b; from.value = a; to.value = b; update(); });
      box.append(btn);
    });

    // police units, grouped by type
    const ub = $("units");
    const tools = document.createElement("div");
    tools.className = "tools";
    const clear = document.createElement("button");
    clear.type = "button"; clear.textContent = "Clear (national total)";
    clear.addEventListener("click", () => { S.units.clear(); ub.querySelectorAll("input").forEach((i) => { i.checked = false; }); update(); });
    tools.append(clear);
    ub.append(tools);
    let lastType = null;
    D.units.forEach((u, i) => {
      if (D.unit_type[i] !== lastType) {
        lastType = D.unit_type[i];
        const g = document.createElement("div"); g.className = "group"; g.textContent = lastType; ub.append(g);
      }
      ub.append(checkbox(u, false, (on) => { on ? S.units.add(u) : S.units.delete(u); update(); }));
    });

    const hb = $("heads");
    const ht = document.createElement("div");
    ht.className = "tools";
    for (const [lab, set] of [["Violent", ["Murder", "Robbery", "Dacoity", "Kidnapping"]],
      ["Recovery", ["Arms Act", "Explosive Act", "Narcotics", "Smuggling"]], ["All", D.heads]]) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = lab;
      b.addEventListener("click", () => {
        S.heads = new Set(set);
        hb.querySelectorAll("input").forEach((i) => { i.checked = S.heads.has(i.value); });
        update();
      });
      ht.append(b);
    }
    hb.append(ht);
    D.heads.forEach((h) => hb.append(checkbox(h, S.heads.has(h), (on, input) => {
      if (on) S.heads.add(h);
      else if (S.heads.size > 1) S.heads.delete(h);
      else input.checked = true;           // keep at least one head
      update();
    }, true)));

    // close a dropdown when clicking elsewhere
    document.addEventListener("click", (e) => {
      document.querySelectorAll("details.multi[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
    });
  }

  function checkbox(value, checked, onChange, swatch) {
    const lab = document.createElement("label");
    const inp = document.createElement("input");
    inp.type = "checkbox"; inp.value = value; inp.checked = checked;
    inp.addEventListener("change", () => onChange(inp.checked, inp));
    lab.append(inp);
    if (swatch) {
      const sw = document.createElement("span");
      sw.className = "swatch"; sw.dataset.head = value;
      lab.append(sw);
    }
    lab.append(document.createTextNode(value));
    return lab;
  }

  function paintSwatches() {
    document.querySelectorAll(".swatch[data-head]").forEach((s) => {
      const st = headStyle(s.dataset.head);
      s.style.background = st.color;
      s.style.opacity = st.dash === "solid" ? 1 : 0.8;
    });
  }

  // ---------------------------------------------------------------- render
  function update() {
    const P = T[theme()];
    const units = unitIdx();
    const heads = D.heads.filter((h) => S.heads.has(h));
    const months = [];
    for (let i = S.from; i <= S.to; i++) months.push(i);
    document.querySelectorAll("#presets button").forEach((b) =>
      b.classList.toggle("on", +b.dataset.a === S.from && +b.dataset.b === S.to));
    $("units-val").textContent = S.units.size ? Array.from(S.units).join(", ") : "All units (national)";
    $("heads-val").textContent = heads.length === D.heads.length ? "All crime heads" : heads.join(", ");
    paintSwatches();

    // totals
    const tot = (c) => months.reduce((s, mi) => s + monthSum(mi, units, col(c)), 0);
    const headsIn = (mi, uis) => heads.reduce((s, h) => s + monthSum(mi, uis, col(h)), 0);
    $("k-total").textContent = fmt(tot("Total Cases"));
    $("k-reported").textContent = fmt(tot("Reported Crime (excl. Recovery)"));
    $("k-heads").textContent = fmt(heads.reduce((s, h) => s + tot(h), 0));
    $("k-recovery").textContent = fmt(tot("Recovery Total"));
    const x = months.map((mi) => D.months[mi]);
    const mark = breakMarker(P);

    // 1 selected heads, month by month
    const trend = heads.map((h) => {
      const st = headStyle(h);
      return { type: "scatter", mode: "lines", name: h, x, y: months.map((mi) => monthSum(mi, units, col(h))),
        line: { color: st.color, width: 2, dash: st.dash },
        hovertemplate: "<b>%{y:,}</b> " + h + "<extra></extra>" };
    });
    Plotly.react("trend", trend, layout({ hovermode: "x unified", shapes: mark.shapes, annotations: mark.annotations,
      xaxis: { hoverformat: "%B %Y" }, yaxis: { tickformat: "~s", rangemode: "tozero" },
      legend: { orientation: "h", x: 0, y: -0.12, font: { color: P.ink2 } } }), CFG);

    // 2 police units ranking (all units; the picked ones highlighted)
    const all = D.units.map((u, ui) => ({ u, v: months.reduce((s, mi) => s + headsIn(mi, [ui]), 0) }))
      .sort((a, b) => a.v - b.v);
    Plotly.react("units-bar", [{ type: "bar", orientation: "h", x: all.map((d) => d.v), y: all.map((d) => d.u),
      marker: { color: all.map((d) => (!S.units.size || S.units.has(d.u)) ? P.cat[0] : P.context), cornerradius: 4 },
      hovertemplate: "%{y}: <b>%{x:,}</b><extra></extra>" }],
    layout({ bargap: 0.25, margin: { l: 120, r: 16, t: 8, b: 32 },
      xaxis: { showgrid: true, tickformat: "~s" }, yaxis: { showgrid: false, dtick: 1, tickfont: { size: 11, color: P.ink2 } } }), CFG);

    // 3 reported crime vs recovery cases
    const rr = [["Total Cases", "All recorded cases", P.cat[6]],
      ["Reported Crime (excl. Recovery)", "Reported crime", P.cat[1]],
      ["Recovery Total", "Recovery cases", P.cat[2]]].map(([c, name, color]) => ({
      type: "scatter", mode: "lines", name, x, y: months.map((mi) => monthSum(mi, units, col(c))),
      line: { color, width: 2.2 }, hovertemplate: "<b>%{y:,}</b> " + name.toLowerCase() + "<extra></extra>" }));
    Plotly.react("rr", rr, layout({ hovermode: "x unified", shapes: mark.shapes, annotations: mark.annotations,
      xaxis: { hoverformat: "%B %Y" }, yaxis: { tickformat: "~s", rangemode: "tozero" },
      legend: { orientation: "h", x: 0, y: -0.12, font: { color: P.ink2 } } }), CFG);

    // 4 map: selected heads per 100,000 people a year, by division
    const perDiv = {};
    units.forEach((ui) => {
      const dv = D.division[ui];
      if (!dv) return;
      perDiv[dv] = (perDiv[dv] || 0) + months.reduce((s, mi) => s + headsIn(mi, [ui]), 0);
    });
    const divs = Object.keys(D.iso);
    const rate = divs.map((d) => (perDiv[d] === undefined ? null
      : perDiv[d] / D.pop[d] * 1e5 * 12 / months.length));
    const rfmt = (v) => (v === null ? "–" : v >= 100 ? v.toFixed(0) : v.toFixed(1));
    const zmax = Math.max(...rate.filter((v) => v !== null), 1e-9);
    Plotly.react("map", [
      { type: "choropleth", geojson: D.geo, featureidkey: "properties.shapeISO",
        locations: divs.map((d) => D.iso[d]), z: rate, customdata: divs,
        colorscale: P.seq.map((c, i) => [i / (P.seq.length - 1), c]), zmin: 0, zmax,
        marker: { line: { color: P.surface, width: 1.5 } },
        hovertemplate: "%{customdata}: <b>%{z:.1f}</b> per 100,000 people a year<extra></extra>",
        colorbar: { thickness: 10, outlinewidth: 0, len: 0.7, tickfont: { color: P.ink2 } } },
      { type: "scattergeo", mode: "text", lon: divs.map((d) => D.anchor[d][0]), lat: divs.map((d) => D.anchor[d][1]),
        text: divs.map((d, i) => "<b>" + d + "</b><br>" + rfmt(rate[i])), hoverinfo: "skip", showlegend: false,
        textfont: { size: 11, family: FONT, shadow: "auto",
          color: rate.map((v) => (v === null ? P.ink : textOn(P.seq, v / zmax))) } },
    ], layout({ margin: { l: 0, r: 0, t: 0, b: 0 },
      geo: { fitbounds: "locations", visible: false, bgcolor: P.surface, projection: { type: "mercator" } } }), CFG);

    // 5 year by year
    const byYear = {};
    months.forEach((mi) => {
      const y = D.months[mi].slice(0, 4);
      byYear[y] = byYear[y] || { v: 0, n: 0 };
      byYear[y].v += headsIn(mi, units);
      byYear[y].n += 1;
    });
    const ys = Object.keys(byYear);
    Plotly.react("years", [{ type: "bar", x: ys, y: ys.map((y) => byYear[y].v),
      customdata: ys.map((y) => byYear[y].n),
      marker: { color: ys.map((y) => (byYear[y].n === 12 ? P.cat[0] : P.faint)), cornerradius: 4 },
      text: ys.map((y) => fmt(byYear[y].v)), textposition: "outside", cliponaxis: false,
      textfont: { color: P.ink, size: 11 },
      hovertemplate: "%{x}: <b>%{y:,}</b> (%{customdata} months)<extra></extra>" }],
    layout({ bargap: 0.3, margin: { l: 52, r: 16, t: 24, b: 32 },
      xaxis: { type: "category", showgrid: false }, yaxis: { tickformat: "~s", rangemode: "tozero" } }), CFG);

    // 6 calendar heatmap of the selected heads
    const years = [...new Set(x.map((m) => +m.slice(0, 4)))];
    const z = years.map(() => new Array(12).fill(null));
    months.forEach((mi) => {
      const iso = D.months[mi], y = +iso.slice(0, 4), m = +iso.slice(5, 7) - 1;
      z[years.indexOf(y)][m] = headsIn(mi, units);
    });
    const cs = P.seq.map((c, i) => [i / (P.seq.length - 1), c]);
    Plotly.react("heat", [{ type: "heatmap", z, x: MONTHS, y: years.map(String), colorscale: cs, xgap: 2, ygap: 2,
      hoverongaps: false, hovertemplate: "%{x} %{y}: <b>%{z:,}</b><extra></extra>",
      colorbar: { thickness: 10, outlinewidth: 0, tickfont: { color: P.ink2 }, tickformat: "~s" } }],
    layout({ margin: { l: 48, r: 8, t: 8, b: 28 }, xaxis: { showgrid: false, type: "category" },
      yaxis: { autorange: "reversed", showgrid: false, type: "category" } }), CFG);

    // 7 share of all cases by crime family
    const fam = {};
    D.heads.forEach((h) => { fam[D.family[h]] = (fam[D.family[h]] || 0) + tot(h); });
    const famTotal = FAMILIES.reduce((s, f) => s + (fam[f] || 0), 0);
    Plotly.react("fam", [{ type: "pie", hole: 0.58, sort: false, direction: "clockwise",
      labels: FAMILIES, values: FAMILIES.map((f) => fam[f] || 0),
      marker: { colors: FAMILIES.map((f) => P.fam[f]), line: { color: P.surface, width: 2 } },
      textinfo: "percent", textposition: "inside", insidetextorientation: "horizontal",
      hovertemplate: "%{label}<br><b>%{value:,}</b> cases (%{percent})<extra></extra>" }],
    layout({ margin: { l: 8, r: 8, t: 8, b: 8 }, showlegend: true,
      legend: { orientation: "v", x: 1, xanchor: "left", y: 0.5, font: { color: P.ink2, size: 12 } },
      annotations: [{ text: "<b>" + fmt(famTotal) + "</b><br>cases", showarrow: false, x: 0.5, y: 0.5,
        xref: "paper", yref: "paper", font: { size: 14, color: P.ink } }] }), CFG);

    // 8 every crime head, log scale
    const mix = D.heads.map((h) => ({ h, v: tot(h) })).sort((a, b) => a.v - b.v);
    Plotly.react("mix", [{ type: "bar", orientation: "h", x: mix.map((d) => Math.max(d.v, 0.9)), y: mix.map((d) => d.h),
      customdata: mix.map((d) => d.v),
      marker: { color: mix.map((d) => S.heads.has(d.h) ? headStyle(d.h).color : P.grid), cornerradius: 4,
        line: { color: mix.map((d) => S.heads.has(d.h) ? P.ink2 : P.axis), width: 0.5 } },
      hovertemplate: "%{y}: <b>%{customdata:,}</b><extra></extra>" }],
    layout({ bargap: 0.25, margin: { l: 170, r: 16, t: 8, b: 32 },
      xaxis: { type: "log", showgrid: true, tickvals: [1, 10, 100, 1e3, 1e4, 1e5, 1e6],
        ticktext: ["1", "10", "100", "1k", "10k", "100k", "1M"] },
      yaxis: { showgrid: false, dtick: 1, tickfont: { size: 11, color: P.ink2 } } }), CFG);
  }

  function start() {
    if (!document.getElementById("overview")) return;   // page without the overview
    fetch("data/explorer.json").then((r) => r.json()).then((d) => {
      D = d;
      buildControls();
      update();
      document.addEventListener("themechange", update);
    }).catch((e) => {
      $("overview").insertAdjacentHTML("afterbegin",
        '<p class="dek">Could not load the data (' + e.message + ").</p>");
    });
  }

  function whenPlotly(cb) {
    if (window.Plotly) return cb();
    const t = setInterval(() => { if (window.Plotly) { clearInterval(t); cb(); } }, 50);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => whenPlotly(start));
  else whenPlotly(start);
})();
