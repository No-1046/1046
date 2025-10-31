// script.js

const api = (p) => `${location.origin}/api${p}`;
let ticker = "6501";
let frame = "1d";
let horizon = 5;
let series = [];
let chart;

function fmt(n, d = 2) { return Number(n).toFixed(d); }
function fmtP(n) { return (Number(n) * 100).toFixed(1) + "%"; }

function monthTickLabels(rows) {
  const labels = [];
  let prev = "";
  for (const r of rows) {
    if (r.xm !== prev) {
      labels.push(r.xm);
      prev = r.xm;
    } else {
      labels.push("");
    }
  }
  return labels;
}

async function loadSeries(years = 10) {
  const url = api(`/series?ticker=${encodeURIComponent(ticker)}&frame=${frame}&years=${years}`);
  const status = document.getElementById("status");
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    series = j.rows;
    document.getElementById("titleName").textContent = `（${j.name} / ${j.ticker}）`;
    status.textContent = `取得: ${series.length}本 / ${j.ticker} / ${frame}`;
  } catch (e) {
    status.textContent = "データ取得に失敗: " + e.message;
    series = [];
    document.getElementById("titleName").textContent = "";
  }
}

function drawChart(predClose = null) {
  const close = series.map(r => r.c);
  const labels = monthTickLabels(series);
  const datasets = [{
    label: "終値",
    data: close,
    borderColor: "#198754", // BootstrapのSuccessカラー
    borderWidth: 2,
    tension: 0.2,
    pointRadius: 0
  }];
  if (predClose != null && close.length) {
    datasets.push({
      label: "予測",
      data: [...Array(close.length - 1).fill(null), close.at(-1), predClose],
      borderColor: "#ffc107", // BootstrapのWarningカラー
      borderDash: [6, 4],
      borderWidth: 2,
      pointRadius: 3
    });
  }
  if (chart) chart.destroy();
  chart = new Chart(document.getElementById("chart"), {
    type: "line",
    data: { labels, datasets },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.1)" },
          ticks: { color: "#adb5bd" }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.1)" },
          ticks: { color: "#adb5bd" }
        }
      }
    }
  });
}

async function loadPredict() {
  const url = api(`/predict/?ticker=${encodeURIComponent(ticker)}&frame=${frame}&years=10&horizon=${horizon}`);
  const status = document.getElementById("status");
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();

    document.getElementById("titleName").textContent = `（${j.name} / ${j.ticker}）`;
    
    // --- ここを修正 ---
    document.getElementById("last").textContent = fmt(j.close, 2);              // j.last_close -> j.close
    document.getElementById("asof").textContent = j.asof;
    document.getElementById("pred").textContent = fmt(j.expected_value, 2);     // j.pred_close -> j.expected_value
    document.getElementById("prob").textContent = fmtP(j.probability);          // j.prob_up -> j.probability, fmtPを使用
    document.getElementById("model").textContent = j.model;
    // --- 修正ここまで ---

    drawChart(j.expected_value); // pred_close -> expected_value
  } catch (e) {
    status.textContent = "予測取得に失敗: " + e.message;
    drawChart(null);
  }
}

async function refreshAll() {
  document.getElementById("searchBtn").disabled = true;
  document.getElementById("status").textContent = "データを読み込んでいます...";
  await loadSeries();
  await loadPredict();
  document.getElementById("searchBtn").disabled = false;
}

// UI handlers
document.getElementById("searchBtn").addEventListener("click", refreshAll);
document.getElementById("tickerInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") refreshAll();
});
document.getElementById("tickerInput").addEventListener("change", (e) => {
  ticker = e.target.value.trim();
});
document.getElementById("frame").addEventListener("change", (e) => {
  frame = e.target.value;
});
document.getElementById("horizon").addEventListener("change", (e) => {
  horizon = Number(e.target.value);
});

// 初期起動
(async function boot() {
  await refreshAll();
})();