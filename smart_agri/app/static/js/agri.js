/* AgriSmartAI front-end: Chart.js bindings + in-silico simulator wiring. */
(function () {
  "use strict";
  var GREEN = "#2f8f63", DARK = "#123528", ORANGE = "#e8590c",
      AMBER = "#b4690e", GRID = "#e7e2d4", MUT = "#7d8471";

  function jd(el, name) {
    try { return JSON.parse(el.getAttribute("data-" + name) || "[]"); }
    catch (e) { return []; }
  }
  function fmt(d) { return String(d).slice(5); }

  function lineChart(id, datasets, fillFirst) {
    var el = document.getElementById(id);
    if (!el || typeof Chart === "undefined") return;
    var labels = jd(el, "labels").map(fmt);
    var ds = datasets.map(function (d, i) {
      return {
        label: d.label, data: jd(el, d.key), borderColor: d.color,
        backgroundColor: (fillFirst && i === 0) ? d.color + "26" : d.color,
        fill: !!(fillFirst && i === 0), tension: 0.35, pointRadius: 0,
        borderWidth: 2, yAxisID: d.axis || "y"
      };
    });
    var scales = {
      x: { grid: { color: GRID }, ticks: { color: MUT, maxTicksLimit: 8, font: { size: 9 } } },
      y: { grid: { color: GRID }, ticks: { color: MUT, font: { size: 9 } } }
    };
    if (datasets.some(function (d) { return d.axis === "y2"; })) {
      scales.y2 = { position: "right", min: 0, max: 1, grid: { drawOnChartArea: false },
                    ticks: { color: MUT, font: { size: 9 } } };
    }
    new Chart(el, {
      type: "line",
      data: { labels: labels, datasets: ds },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: MUT, boxWidth: 10, font: { size: 10 } } } },
        scales: scales
      }
    });
  }

  function ring(id) {
    var el = document.getElementById(id);
    if (!el || typeof Chart === "undefined") return;
    var v = parseFloat(el.getAttribute("data-val") || 0);
    new Chart(el, {
      type: "doughnut",
      data: { labels: ["confidence", "band"],
        datasets: [{ data: [v, 100 - v], backgroundColor: [GREEN, "#ece8db"],
          borderWidth: 0, cutout: "74%" }] },
      options: { responsive: false, plugins: { legend: { display: false },
        tooltip: { enabled: false } } },
      plugins: [{
        id: "txt",
        afterDraw: function (c) {
          var x = c.ctx;
          x.save();
          x.font = "800 20px ui-monospace, Menlo, monospace";
          x.fillStyle = DARK; x.textAlign = "center"; x.textBaseline = "middle";
          x.fillText(v.toFixed(0) + "%", c.width / 2, c.height / 2);
          x.restore();
        }
      }]
    });
  }

  function simulate(btn) {
    var field = btn.getAttribute("data-field");
    var p = document.getElementById("pathogen"), i = document.getElementById("irrig"),
        f = document.getElementById("fungi");
    var body = {
      field_id: field,
      pathogen_delta: p ? p.value : 12,
      irrigation_delta: i ? i.value : 30,
      fungicide: f ? f.checked : true
    };
    btn.disabled = true; btn.textContent = "Running twin…";
    fetch("/api/twin/simulate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (d) {
      var rec = document.getElementById("recovery");
      if (rec) rec.innerHTML = d.recovery.toFixed(0) + "<span style='font-size:13px'>/100</span>";
      var delta = document.getElementById("simdelta");
      if (delta) delta.innerHTML =
        "Δ health " + (d.delta_health >= 0 ? "+" : "") + d.delta_health +
        " · Δ yield " + (d.delta_yield_q >= 0 ? "+" : "") + d.delta_yield_q +
        " q · stress " + (d.peak_water_stress * 100).toFixed(0) + "% · logged to sim_runs";
    }).catch(function (e) {
      var delta = document.getElementById("simdelta");
      if (delta) delta.textContent = "simulator error: " + e;
    }).finally(function () {
      btn.disabled = false; btn.textContent = btn.id === "runSim" ? "Execute In-Silico Forecast" : "Run Scenario →";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    lineChart("stageChart", [
      { key: "values", label: "NDVI (twin)", color: GREEN },
      { key: "health", label: "Health /100", color: AMBER, axis: "y2" }
    ], true);
    lineChart("twinChart", [
      { key: "health", label: "Canopy health", color: GREEN },
      { key: "stress", label: "Water stress", color: ORANGE, axis: "y2" }
    ], true);
    lineChart("marketChart", [{ key: "values", label: "Modal ₹/q", color: DARK }], true);
    lineChart("cropChart", [
      { key: "values", label: "NDVI (twin)", color: GREEN },
      { key: "health", label: "Health /100", color: AMBER, axis: "y2" }
    ], true);
    lineChart("wxChart", [
      { key: "values", label: "Rainfall mm", color: "#2b5f8f" },
      { key: "health", label: "Tmax °C", color: ORANGE, axis: "y2" }
    ], true);
    ring("confRing");

    ["runSim", "runSim2"].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) b.addEventListener("click", function () { simulate(b); });
    });
    var p = document.getElementById("pathogen"), pv = document.getElementById("pval");
    if (p && pv) p.addEventListener("input", function () { pv.textContent = p.value; });
    var ir = document.getElementById("irrig"), iv = document.getElementById("ival");
    if (ir && iv) ir.addEventListener("input", function () { iv.textContent = ir.value; });
  });
})();
