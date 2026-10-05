/* Renders every chart on the story page.
 *
 * Each <div class="chart" data-id="..."> loads charts/<theme>/<id>.json when it
 * scrolls near the viewport. The JSON holds a Plotly figure or a Vega-Lite
 * spec, plus optional "controls" (Plotly) that become <select> menus in the
 * figure's .controls row. Switching theme re-renders charts from the other
 * theme's JSON and keeps each chart's current menu choices.
 */
(function () {
  "use strict";
  const root = document.documentElement;
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const theme = () => root.dataset.theme || (mq.matches ? "dark" : "light");

  const cache = new Map();
  const state = new Map();     // id -> {sel, view, J, theme, width}
  const rendered = new Set();

  function getSpec(id, t) {
    const key = t + "/" + id;
    if (!cache.has(key)) {
      cache.set(key, fetch("charts/" + t + "/" + id + ".json").then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }));
    }
    return cache.get(key);
  }

  const plotlyConfig = (id) => ({
    responsive: true,
    displaylogo: false,
    displayModeBar: "hover",
    modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines",
      "hoverClosestCartesian", "hoverCompareCartesian", "hoverClosestGeo"],
    toImageButtonOptions: { format: "png", filename: "bd-crime-" + id, scale: 2 },
  });

  async function applyOption(gd, opt) {
    for (const [patch, idx] of opt.restyle || []) await Plotly.restyle(gd, patch, idx);
    if (opt.relayout && Object.keys(opt.relayout).length) await Plotly.relayout(gd, opt.relayout);
  }

  function controlsBox(id) {
    return document.querySelector('.controls[data-for="' + id + '"]');
  }

  function buildSelects(id, el, st) {
    const box = controlsBox(id);
    if (!box || box.dataset.built) return;
    box.dataset.built = "1";
    st.J.controls.forEach((c, i) => {
      const label = document.createElement("label");
      const span = document.createElement("span");
      span.textContent = c.label;
      const sel = document.createElement("select");
      c.options.forEach((o, k) => {
        const op = document.createElement("option");
        op.value = String(k);
        op.textContent = o.label;
        sel.appendChild(op);
      });
      sel.value = String(st.sel[i]);
      sel.addEventListener("change", async () => {
        st.sel[i] = +sel.value;
        el.classList.add("busy");
        await applyOption(el, st.J.controls[i].options[st.sel[i]]);
        el.classList.remove("busy");
      });
      label.append(span, sel);
      box.insertBefore(label, box.firstChild);
    });
  }

  async function renderPlotly(el, id, J, st) {
    st.J = J;
    if (!st.sel) st.sel = (J.controls || []).map((c) => c.default);
    if (J.controls && J.controls.length) buildSelects(id, el, st);
    const spec = J.spec;
    const ld = el.querySelector(".loading");
    if (ld) ld.remove();
    await Plotly.react(el, { data: spec.data, layout: spec.layout, frames: spec.frames || [],
      config: plotlyConfig(id) });
    for (let i = 0; i < (J.controls || []).length; i++) {
      if (st.sel[i] !== J.controls[i].default) await applyOption(el, J.controls[i].options[st.sel[i]]);
    }
  }

  function fitVega(spec, fit, w) {
    if (fit === "vconcat") {
      (spec.vconcat || []).forEach((s) => { s.width = Math.max(260, w - 96); });
    } else if (fit === "facet") {
      const cols = w < 520 ? 1 : w < 860 ? 2 : 4;
      spec.columns = cols;
      if (spec.spec) spec.spec.width = Math.max(150, Math.floor((w - 10) / cols) - 58);
    }
  }

  async function renderVega(el, id, J, st, t) {
    const spec = JSON.parse(JSON.stringify(J.spec));
    const w = el.clientWidth || 800;
    st.width = w;
    fitVega(spec, J.fit, w);
    // keep the reader's choices in bound menus/radios across re-renders
    if (st.view) {
      for (const p of spec.params || []) {
        if (p.bind && p.bind !== "legend" && !p.select) {
          try { p.value = st.view.signal(p.name); } catch (e) { /* not a signal */ }
        }
      }
      st.view.finalize();
      st.view = null;
    }
    const box = controlsBox(id);
    if (box) box.querySelectorAll(".vega-bindings").forEach((n) => n.remove());
    el.innerHTML = "";
    let bindEl = null;
    if (box && (spec.params || []).some((p) => p.bind && p.bind !== "legend")) {
      bindEl = document.createElement("div");
      bindEl.className = "vega-bindings";
      box.insertBefore(bindEl, box.firstChild);
    }
    const res = await vegaEmbed(el, spec, {
      actions: { export: true, source: false, compiled: false, editor: false },
      renderer: "svg",
      tooltip: { theme: t },
      bind: bindEl || undefined,
      downloadFileName: "bd-crime-" + id,
    });
    st.view = res.view;
  }

  async function render(el) {
    const id = el.dataset.id;
    const t = theme();
    const st = state.get(id) || {};
    state.set(id, st);
    st.theme = t;
    let J;
    try {
      J = await getSpec(id, t);
    } catch (e) {
      el.innerHTML = '<div class="loading">Could not load this chart (' + e.message + ").</div>";
      return;
    }
    if (st.theme !== t) return;          // theme changed while loading
    const minw = +el.dataset.minw || 0;
    if (minw) el.style.minWidth = minw + "px";
    try {
      if (J.kind === "plotly") await renderPlotly(el, id, J, st);
      else await renderVega(el, id, J, st, t);
      el.style.minHeight = "";
      rendered.add(el);
    } catch (e) {
      console.error(id, e);
      el.innerHTML = '<div class="loading">Chart failed to render.</div>';
    }
  }

  function whenLibs(cb) {
    const ok = () => window.Plotly && window.vegaEmbed;
    if (ok()) return cb();
    const timer = setInterval(() => { if (ok()) { clearInterval(timer); cb(); } }, 60);
  }

  function start() {
    const charts = Array.from(document.querySelectorAll(".chart[data-id]"));
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) { io.unobserve(e.target); render(e.target); }
      }
    }, { rootMargin: "700px 0px" });
    charts.forEach((c) => io.observe(c));

    // vconcat / facet Vega charts are sized in JS: re-render when their width changes
    let rt = null;
    window.addEventListener("resize", () => {
      clearTimeout(rt);
      rt = setTimeout(() => {
        for (const el of rendered) {
          const st = state.get(el.dataset.id);
          if (st && st.J === undefined && st.view && Math.abs(el.clientWidth - st.width) > 40) render(el);
        }
      }, 250);
    });
  }

  function rerenderAll() {
    for (const el of rendered) render(el);
  }

  document.addEventListener("click", (e) => {
    const b = e.target.closest(".theme-toggle");
    if (!b) return;
    const t = theme() === "dark" ? "light" : "dark";
    root.dataset.theme = t;
    try { localStorage.setItem("theme", t); } catch (err) { /* storage blocked */ }
    rerenderAll();
    document.dispatchEvent(new CustomEvent("themechange"));
  });
  mq.addEventListener("change", () => {
    if (!root.dataset.theme) { rerenderAll(); document.dispatchEvent(new CustomEvent("themechange")); }
  });

  if (document.querySelector(".chart[data-id]")) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => whenLibs(start));
    else whenLibs(start);
  }
})();
