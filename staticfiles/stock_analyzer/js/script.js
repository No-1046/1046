// script.js

const api = (p) => `${location.origin}/api${p}`;
let ticker = "6501";
let frame  = "1d";
let horizon = 5;
let series = [];
let chart;

// --- 修正: 安全でカンマ区切り対応のフォーマット関数 ---
function fmt(n, d=2) { 
  if (n === null || n === undefined || isNaN(n)) return "--";
  return Number(n).toFixed(d); 
}

// 確率用のfmtP関数
function fmtP(n) { 
  if (n === null || n === undefined || isNaN(n)) return "--%";
  return (Number(n) * 100).toFixed(1) + "%"; 
}

function monthTickLabels(rows){
  const labels = [];
  let prev = "";
  for(const r of rows){
    if (r.xm !== prev){
      labels.push(r.xm);
      prev = r.xm;
    } else {
      labels.push("");
    }
  }
  return labels;
}

async function loadSeries(years=10){
  const url = api(`/series?ticker=${encodeURIComponent(ticker)}&frame=${frame}&years=${years}`);
  const status = document.getElementById("status");
  try{
    const res = await fetch(url);
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    series = j.rows;
    
    const titleEl = document.getElementById("titleName");
    if(titleEl) titleEl.textContent = `（${j.name} / ${j.ticker}）`;
    
    status.textContent = `取得: ${series.length}本 / ${j.ticker} / ${frame}`;
  }catch(e){
    status.textContent = "データ取得に失敗: " + e.message;
    series = [];
    const titleEl = document.getElementById("titleName");
    if(titleEl) titleEl.textContent = "";
  }
}

function drawChart(predClose=null){
  const close = series.map(r=>r.c);
  // ラベル生成（簡易版）
  const labels = series.map(r => r.t || ""); 

  const datasets = [{
    label: "終値",
    data: close,
    borderColor: "#198754",
    borderWidth: 2,
    tension: 0.2,
    pointRadius: 0
  }];
  
  if (predClose != null && close.length){
    datasets.push({
      label: "予測",
      data: [...Array(close.length-1).fill(null), close.at(-1), predClose],
      borderColor: "#ffc107",
      borderDash: [6,4], 
      borderWidth: 2, 
      pointRadius: 4
    });
  }
  
  const ctx = document.getElementById("chart");
  if (!ctx) return;

  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false }},
      scales: {
        x: { grid: { color: "rgba(148,163,184,0.15)" }, ticks: { color:"#cbd5e1", maxTicksLimit: 12 } },
        y: { grid: { color: "rgba(148,163,184,0.15)" }, ticks: { color:"#cbd5e1" } }
      }
    }
  });
}

async function loadPredict(){
  const url = api(`/predict?ticker=${encodeURIComponent(ticker)}&frame=${frame}&years=10&horizon=${horizon}`);
  const status = document.getElementById("status");
  try{
    const r = await fetch(url);
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();

    // デバッグ用ログ
    console.log("API Response:", j);

    // タイトル更新
    if(j.name) document.getElementById("titleName").textContent = `（${j.name} / ${j.ticker}）`;

    // --- 修正: キー名をサーバーのレスポンス(JSON)に合わせる ---
    // last_close  -> close
    // pred_close  -> expected_value
    // prob_up     -> probability
    document.getElementById("last").textContent  = fmt(j.last_close, 2);
    document.getElementById("asof").textContent  = j.asof;
    document.getElementById("pred").textContent  = fmt(j.pred_close,2);
    document.getElementById("prob").textContent  = fmtP(j.prob_up);
    document.getElementById("model").textContent = j.model;

    // チャート描画にも正しいキーを渡す
    drawChart(j.expected_value);

  }catch(e){
    console.error(e);
    status.textContent = "予測取得に失敗: " + e.message;
    drawChart(null);
  }
}

async function refreshAll(){
  const btn = document.getElementById("searchBtn");
  if(btn) btn.disabled = true;
  
  await loadSeries();
  await loadPredict();
  
  if(btn) btn.disabled = false;
}

// UI handlers
document.getElementById("searchBtn").addEventListener("click", refreshAll);
document.getElementById("tickerInput").addEventListener("keydown", (e)=>{
  if(e.key==="Enter") refreshAll();
});
document.getElementById("tickerInput").addEventListener("change", (e)=>{
  ticker = e.target.value.trim();
});
document.getElementById("frame").addEventListener("change", (e)=>{
  frame = e.target.value;
});
document.getElementById("horizon").addEventListener("change", (e)=>{
  horizon = Number(e.target.value);
});

// 初期起動
(async function boot(){
  await refreshAll();
})();