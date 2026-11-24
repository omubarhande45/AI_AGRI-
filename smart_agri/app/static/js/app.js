/* Chart.js setup for the SmartAgri dashboard.
   Every chart is fed by a small JSON blob that the page template inlines, so
   there are no extra round-trips and the page works fully offline. */
(function () {
  "use strict";

  if (typeof Chart === "undefined") { console.warn("Chart.js not loaded"); return; }

  const C = {
    green: "#3ecf6e", green2: "#2aa955", leaf: "#7fd694",
    amber: "#f0b429", red: "#ef5f5f", blue: "#4aa8e0", purple: "#a98bf0",
    grid: "rgba(147,169,154,.14)", text: "#93a99a", dim: "#6d8478"
  };
  const PALETTE = [C.green, C.blue, C.amber, C.purple, C.red, C.leaf, "#e08a4a", "#5fd0c4"];

  Chart.defaults.color = C.text;
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.labels.boxWidth = 11;
  Chart.defaults.plugins.legend.labels.boxHeight = 11;
  Chart.defaults.plugins.tooltip.backgroundColor = "rgba(13,21,18,.95)";
  Chart.defaults.plugins.tooltip.borderColor = "rgba(62,207,110,.35)";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.maintainAspectRatio = false;

  const axes = (opts = {}) => ({
    x: Object.assign({ grid: { color: C.grid, drawBorder: false },
                       ticks: { maxTicksLimit: 10, maxRotation: 0, autoSkip: true } }, opts.x || {}),
    y: Object.assign({ grid: { color: C.grid, drawBorder: false },
                       ticks: { maxTicksLimit: 6 } }, opts.y || {})
  });
  const el = id => document.getElementById(id);
  const mk = (id, cfg) => { const e = el(id); if (e) new Chart(e, cfg); };
  const d = s => (s || "").slice(5);

  /* ------------------------------------------------ dashboard */
  if (window.DASH) {
    const w = window.DASH.weather || [];
    mk("wxChart", {
      type: "bar",
      data: {
        labels: w.map(x => d(x.date)),
        datasets: [
          { type: "line", label: "Max °C", data: w.map(x => x.temp_max), borderColor: C.red,
            backgroundColor: "transparent", tension: .35, yAxisID: "y", pointRadius: 2 },
          { type: "line", label: "Min °C", data: w.map(x => x.temp_min), borderColor: C.blue,
            backgroundColor: "transparent", tension: .35, yAxisID: "y", pointRadius: 2 },
          { type: "bar", label: "Rain mm", data: w.map(x => x.rainfall_mm),
            backgroundColor: "rgba(74,168,224,.55)", yAxisID: "y1", borderRadius: 3 }
        ]
      },
      options: {
        scales: {
          x: axes().x,
          y: { position: "left", grid: { color: C.grid }, ticks: { callback: v => v + "°" } },
          y1: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true,
                ticks: { callback: v => v + "mm" } }
        }
      }
    });

    const p = window.DASH.prices || [];
    mk("priceChart", {
      type: "line",
      data: {
        labels: (p[0] && p[0].series ? p[0].series.map((_, i) => i) : []),
        datasets: p.map((s, i) => ({
          label: s.crop, data: s.series, borderColor: PALETTE[i % PALETTE.length],
          backgroundColor: "transparent", tension: .3, pointRadius: 0, borderWidth: 2
        }))
      },
      options: { scales: axes({ y: { ticks: { callback: v => "₹" + Math.round(v) } } }),
                 interaction: { mode: "index", intersect: false } }
    });
  }

  /* ------------------------------------------------ crop detail / twin */
  function twinCharts(sim, mainId, canopyId, waterId) {
    if (!sim || !sim.trajectory) return;
    const t = sim.trajectory;
    if (mainId) mk(mainId, {
      type: "line",
      data: {
        labels: t.map(x => d(x.date)),
        datasets: [
          { label: "Yield (kg/ha)", data: t.map(x => x.yield_kg_ha), borderColor: C.green,
            backgroundColor: "rgba(62,207,110,.12)", fill: true, tension: .3, pointRadius: 0, yAxisID: "y" },
          { label: "NDVI", data: t.map(x => x.ndvi), borderColor: C.leaf,
            backgroundColor: "transparent", tension: .3, pointRadius: 0, yAxisID: "y1" },
          { label: "Health", data: t.map(x => x.health_score), borderColor: C.amber,
            backgroundColor: "transparent", borderDash: [5, 4], tension: .3, pointRadius: 0, yAxisID: "y1" }
        ]
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: axes().x,
          y: { position: "left", grid: { color: C.grid }, title: { display: true, text: "kg/ha" } },
          y1: { position: "right", min: 0, max: 100, grid: { drawOnChartArea: false } } }
      }
    });
    if (canopyId) mk(canopyId, {
      type: "line",
      data: {
        labels: t.map(x => d(x.date)),
        datasets: [
          { label: "LAI", data: t.map(x => x.lai), borderColor: C.green,
            backgroundColor: "rgba(62,207,110,.15)", fill: true, tension: .3, pointRadius: 0 },
          { label: "Biomass (t/ha)", data: t.map(x => x.biomass_kg_ha / 1000),
            borderColor: C.purple, backgroundColor: "transparent", tension: .3, pointRadius: 0, yAxisID: "y1" },
          { label: "GDD", data: t.map(x => x.gdd), borderColor: C.dim,
            backgroundColor: "transparent", borderDash: [3, 3], tension: .3, pointRadius: 0, yAxisID: "y2" }
        ]
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: axes().x,
          y: { grid: { color: C.grid }, title: { display: true, text: "LAI" } },
          y1: { position: "right", grid: { drawOnChartArea: false } },
          y2: { display: false } }
      }
    });
    if (waterId) mk(waterId, {
      type: "line",
      data: {
        labels: t.map(x => d(x.date)),
        datasets: [
          { label: "Soil water (mm)", data: t.map(x => x.soil_water_mm), borderColor: C.blue,
            backgroundColor: "rgba(74,168,224,.16)", fill: true, tension: .25, pointRadius: 0 },
          { label: "Rain (mm)", data: t.map(x => x.rain_mm), type: "bar",
            backgroundColor: "rgba(74,168,224,.4)", yAxisID: "y1", borderRadius: 2 },
          { label: "Water stress", data: t.map(x => x.water_stress * 100), borderColor: C.red,
            backgroundColor: "transparent", borderDash: [4, 3], tension: .2, pointRadius: 0, yAxisID: "y2" }
        ]
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: axes().x,
          y: { grid: { color: C.grid }, title: { display: true, text: "mm" } },
          y1: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true },
          y2: { display: false, min: 0, max: 100 } }
      }
    });
  }
  if (window.TWIN) twinCharts(window.TWIN, "twinChart", null, null);
  if (window.SIM) twinCharts(window.SIM, "twinMain", "twinCanopy", "twinWater");

  if (window.SOIL && window.SOIL.length) {
    mk("soilChart", {
      type: "line",
      data: {
        labels: window.SOIL.map(s => s.recorded_at),
        datasets: [
          { label: "N", data: window.SOIL.map(s => s.nitrogen), borderColor: C.green, tension: .3, pointRadius: 3 },
          { label: "P", data: window.SOIL.map(s => s.phosphorus), borderColor: C.blue, tension: .3, pointRadius: 3 },
          { label: "K", data: window.SOIL.map(s => s.potassium), borderColor: C.amber, tension: .3, pointRadius: 3 },
          { label: "Moisture %", data: window.SOIL.map(s => s.moisture), borderColor: C.purple,
            borderDash: [4, 3], tension: .3, pointRadius: 3 }
        ]
      },
      options: { scales: axes() }
    });
  }

  /* ------------------------------------------------ market */
  if (window.MKT) {
    const h = window.MKT.history || [];
    const series = window.MKT.series || {};
    const names = Object.keys(series);
    mk("priceMain", {
      type: "line",
      data: {
        labels: h.map(x => d(x.date)),
        datasets: names.map((n, i) => ({
          label: n.replace(" APMC", ""), data: series[n], borderColor: PALETTE[i % PALETTE.length],
          backgroundColor: "transparent", tension: .25, pointRadius: 0, borderWidth: 1.6
        })).concat(h.length ? [{
          label: "All-mandi average", data: h.map(x => x.modal_price), borderColor: "#ffffff",
          backgroundColor: "rgba(255,255,255,.06)", fill: true, tension: .25,
          pointRadius: 0, borderWidth: 2.4
        }] : [])
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: axes({ y: { ticks: { callback: v => "₹" + Math.round(v) } } })
      }
    });

    const cost = window.MKT.cost || {};
    const labels = Object.keys(cost);
    if (labels.length) mk("costChart", {
      type: "doughnut",
      data: { labels,
        datasets: [{ data: labels.map(k => cost[k]),
          backgroundColor: PALETTE, borderColor: "#16241d", borderWidth: 2 }] },
      options: { plugins: { legend: { position: "right" } }, cutout: "58%" }
    });
  }

  /* ------------------------------------------------ weather */
  if (window.WX) {
    const h = window.WX.history || [];
    mk("tempChart", {
      type: "line",
      data: { labels: h.map(x => d(x.date)),
        datasets: [
          { label: "Max °C", data: h.map(x => x.temp_max), borderColor: C.red,
            backgroundColor: "rgba(239,95,95,.10)", fill: true, tension: .3, pointRadius: 0 },
          { label: "Min °C", data: h.map(x => x.temp_min), borderColor: C.blue,
            backgroundColor: "rgba(74,168,224,.10)", fill: true, tension: .3, pointRadius: 0 }
        ] },
      options: { interaction: { mode: "index", intersect: false }, scales: axes() }
    });
    mk("rainChart", {
      type: "bar",
      data: { labels: h.map(x => d(x.date)),
        datasets: [{ label: "Rainfall (mm)", data: h.map(x => x.rainfall_mm),
          backgroundColor: "rgba(74,168,224,.6)", borderRadius: 2 }] },
      options: { scales: axes({ y: { beginAtZero: true } }) }
    });
  }

  /* ------------------------------------------------ DSS */
  if (window.DSS) {
    const f = window.DSS.fields || [];
    const keys = ["nutrition", "water", "protection", "disease", "vigour"];
    mk("healthChart", {
      type: "radar",
      data: {
        labels: keys.map(k => k[0].toUpperCase() + k.slice(1)),
        datasets: f.slice(0, 6).map((x, i) => ({
          label: x.field, data: keys.map(k => x.sub_scores[k]),
          borderColor: PALETTE[i % PALETTE.length],
          backgroundColor: PALETTE[i % PALETTE.length] + "22",
          pointRadius: 2, borderWidth: 2
        }))
      },
      options: {
        scales: { r: { min: 0, max: 100, grid: { color: C.grid },
          angleLines: { color: C.grid }, pointLabels: { color: C.text },
          ticks: { display: false } } }
      }
    });
  }

  /* ------------------------------------------------ upload UX */
  const dz = document.getElementById("dropZone");
  const fi = document.getElementById("leaf_image");
  if (dz && fi) {
    fi.addEventListener("change", () => {
      const f = fi.files[0];
      if (f) dz.querySelector("div:nth-child(2)").innerHTML =
        "<strong>" + f.name + "</strong> (" + (f.size / 1e6).toFixed(1) + " MB)";
    });
    ["dragover", "dragenter"].forEach(ev => dz.addEventListener(ev, e => {
      e.preventDefault(); dz.style.borderColor = "#3ecf6e";
    }));
    ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => {
      e.preventDefault(); dz.style.borderColor = "";
      if (ev === "drop" && e.dataTransfer.files.length) {
        fi.files = e.dataTransfer.files;
        fi.dispatchEvent(new Event("change"));
      }
    }));
  }
})();
