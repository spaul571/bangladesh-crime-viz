/* Crime explorer: the web version of the Dash dashboard (dashboard/app.py).
 *
 * One filter row (period, police units, crime heads) scopes the KPI tiles,
 * the four charts and the table. Everything is computed in the browser from
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
      axis: "#c3c2b7", context: "#a8a79f",
      cat: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
      seq: ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6",
        "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"] },
    dark: { surface: "#1a1a19", ink: "#ffffff", ink2: "#c3c2b7", muted: "#898781", grid: "#2c2c2a",
      axis: "#383835", context: "#6b6a65",
      cat: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
      seq: ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7",
        "#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb"] },
  };
  // Eight focus heads own the categorical slots; the rest are grey with distinct dashes.
  const FOCUS = ["Murder", "Robbery", "Dacoity", "Kidnapping", "Woman & Child Repression",
    "Narcotics", "Theft", "Arms Act"];
  const DASHES = ["dot", "dash", "longdash", "dashdot", "longdashdot", "5px,2px", "2px,6px"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const BREAK = "2024-08-05";

  let D = null;
  const S = { from: 0, to: 0, units: new Set(), heads: new Set(["Murder", "Robbery", "Dacoity", "Kidnapping"]),
    sort: { col: 0, dir: 1 } };
  const $ = (id) => document.getElementById(id);
  const fmt = (v) => Math.round(v).toLocaleString("en-US");
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
    from.addEventListener("change", () => { S.from = +from.value; if (S.from > S.to) { S.to = S.from; to.value = S.to; } preset(null); update(); });
    to.addEventListener("change", () => { S.to = +to.value; if (S.to < S.from) { S.from = S.to; from.value = S.from; } preset(null); update(); });
    const idx = (iso) => D.months.indexOf(iso);
    const presets = {
      all: [0, D.months.length - 1],
      pre: [idx("2022-08-31"), idx("2024-07-31")],
      post: [idx("2024-09-30"), D.months.length - 1],
      last12: [D.months.length - 12, D.months.length - 1],
    };
    document.querySelectorAll(".presets button").forEach((b) => b.addEventListener("click", () => {
      [S.from, S.to] = presets[b.dataset.preset];
      from.value = S.from; to.value = S.to;
      preset(b.dataset.preset); update();
    }));

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
    $("csv").addEventListener("click", downloadCsv);
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

  function preset(name) {
    document.querySelectorAll(".presets button").forEach((b) => b.classList.toggle("on", b.dataset.preset === name));
  }

  // ---------------------------------------------------------------- render
  function update() {
    const P = T[theme()];
    const units = unitIdx();
    const heads = D.heads.filter((h) => S.heads.has(h));
    const months = [];
    for (let i = S.from; i <= S.to; i++) months.push(i);
    $("units-val").textContent = S.units.size ? Array.from(S.units).join(", ") : "All units (national)";
    $("heads-val").textContent = heads.length === D.heads.length ? "All crime heads" : heads.join(", ");
    paintSwatches();

    // KPIs
    const tot = (c) => months.reduce((s, mi) => s + monthSum(mi, units, col(c)), 0);
    $("k-total").textContent = fmt(tot("Total Cases"));
    $("k-reported").textContent = fmt(tot("Reported Crime (excl. Recovery)"));
    $("k-heads").textContent = fmt(heads.reduce((s, h) => s + tot(h), 0));
    $("k-recovery").textContent = fmt(tot("Recovery Total"));

    // trend
    const x = months.map((mi) => D.months[mi]);
    const trend = heads.map((h) => {
      const st = headStyle(h);
      return { type: "scatter", mode: "lines", name: h, x, y: months.map((mi) => monthSum(mi, units, col(h))),
        line: { color: st.color, width: 2, dash: st.dash },
        hovertemplate: "<b>%{y:,}</b> " + h + "<extra></extra>" };
    });
    const shapes = [], annotations = [];
    if (BREAK >= D.months[S.from].slice(0, 8) + "01" && BREAK <= D.months[S.to]) {
      shapes.push({ type: "line", x0: BREAK, x1: BREAK, yref: "paper", y0: 0, y1: 1, line: { color: P.ink2, width: 1 } });
      annotations.push({ x: BREAK, y: 1, yref: "paper", text: "5 Aug 2024", showarrow: false, xanchor: "left",
        yanchor: "top", xshift: 4, font: { size: 11, color: P.ink2 } });
    }
    Plotly.react("trend", trend, layout({ hovermode: "x unified", shapes, annotations,
      xaxis: { hoverformat: "%B %Y" }, yaxis: { tickformat: "~s", rangemode: "tozero" },
      legend: { orientation: "h", x: 0, y: -0.12, font: { color: P.ink2 } } }), CFG);

    // units ranking (all units; selection highlighted)
    const all = D.units.map((u, ui) => ({ u, v: months.reduce((s, mi) =>
      s + heads.reduce((a, h) => a + D.values[mi][ui][col(h)], 0), 0) })).sort((a, b) => a.v - b.v);
    Plotly.react("units-bar", [{ type: "bar", orientation: "h", x: all.map((d) => d.v), y: all.map((d) => d.u),
      marker: { color: all.map((d) => (!S.units.size || S.units.has(d.u)) ? P.cat[0] : P.context), cornerradius: 4 },
      hovertemplate: "%{y}: <b>%{x:,}</b><extra></extra>" }],
    layout({ bargap: 0.25, margin: { l: 120, r: 16, t: 8, b: 32 },
      xaxis: { showgrid: true, tickformat: "~s" }, yaxis: { showgrid: false, dtick: 1, tickfont: { size: 11, color: P.ink2 } } }), CFG);

    // calendar heatmap of the selected heads
    const years = [...new Set(x.map((m) => +m.slice(0, 4)))];
    const z = years.map(() => new Array(12).fill(null));
    months.forEach((mi) => {
      const iso = D.months[mi], y = +iso.slice(0, 4), m = +iso.slice(5, 7) - 1;
      z[years.indexOf(y)][m] = heads.reduce((s, h) => s + monthSum(mi, units, col(h)), 0);
    });
    const cs = P.seq.map((c, i) => [i / (P.seq.length - 1), c]);
    Plotly.react("heat", [{ type: "heatmap", z, x: MONTHS, y: years.map(String), colorscale: cs, xgap: 2, ygap: 2,
      hoverongaps: false, hovertemplate: "%{x} %{y}: <b>%{z:,}</b><extra></extra>",
      colorbar: { thickness: 10, outlinewidth: 0, tickfont: { color: P.ink2 }, tickformat: "~s" } }],
    layout({ margin: { l: 48, r: 8, t: 8, b: 28 }, xaxis: { showgrid: false, type: "category" },
      yaxis: { autorange: "reversed", showgrid: false, type: "category" } }), CFG);

    // crime mix, every head, log scale
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

    renderTable(months, units, heads);
  }

  let TABLE = { head: [], rows: [] };
  function renderTable(months, units, heads) {
    const cols = ["Month tag"].concat(heads, ["Total Cases"]);
    const rows = months.map((mi) => {
      const iso = D.months[mi];
      const d = new Date(iso + "T00:00:00");
      const tag = String(d.getDate()).padStart(2, "0") + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
      return [{ s: iso, t: tag }].concat(heads.concat(["Total Cases"]).map((h) => monthSum(mi, units, col(h))));
    });
    TABLE = { head: cols, rows };
    drawTable();
  }

  function drawTable() {
    const { col: c, dir } = S.sort;
    const rows = TABLE.rows.slice().sort((a, b) => {
      const va = c === 0 ? a[0].s : a[c], vb = c === 0 ? b[0].s : b[c];
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir;
    });
    const tbl = $("table");
    tbl.textContent = "";
    const thead = tbl.createTHead().insertRow();
    TABLE.head.forEach((h, i) => {
      const th = document.createElement("th");
      th.textContent = h;
      th.tabIndex = 0;
      if (i === c) th.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
      const sortBy = () => { S.sort = { col: i, dir: i === c ? -dir : (i === 0 ? 1 : -1) }; drawTable(); };
      th.addEventListener("click", sortBy);
      th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sortBy(); } });
      thead.append(th);
    });
    const body = tbl.createTBody();
    rows.forEach((r) => {
      const tr = body.insertRow();
      r.forEach((v, i) => { tr.insertCell().textContent = i === 0 ? v.t : fmt(v); });
    });
  }

  function downloadCsv() {
    const esc = (s) => /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    const unitNote = S.units.size ? Array.from(S.units).join("; ") : "All units (national)";
    const lines = ["# Police units: " + unitNote, TABLE.head.map(esc).join(",")];
    TABLE.rows.forEach((r) => lines.push([r[0].s].concat(r.slice(1)).join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "bd-crime-selection.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function start() {
    if (!document.getElementById("dashboard")) return;   // page without the dashboard
    fetch("data/explorer.json").then((r) => r.json()).then((d) => {
      D = d;
      buildControls();
      update();
      document.addEventListener("themechange", update);
    }).catch((e) => {
      document.querySelector(".kpis").insertAdjacentHTML("beforebegin",
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
