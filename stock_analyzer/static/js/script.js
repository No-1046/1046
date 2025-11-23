// script.js

const api = (p) => `${location.origin}/api${p}`;
let ticker = "6501";
let frame = "1d";
let horizon = 5;
let series = [];
let chart;

// 数値フォーマット関数（入力がnull/undefinedの場合は"--"を返すように安全化）
function fmt(n, d = 2) {
  if (n === null || n === undefined || isNaN(n) || n === "" || !isFinite(n)) {
      console.warn(`[FMT WARN] Input is not a valid number: ${n}`);
      return "--";
  }
  return Number(n).toFixed(d);
}

function fmtP(n) {
  if (n === null || n === undefined || isNaN(n) || n === "" || !isFinite(n)) {
      console.warn(`[FMT WARN] Probability input is not valid: ${n}`);
      return "--%";
  }
  return (Number(n) * 100).toFixed(1) + "%";
}
// (月ごとのラベルを生成する monthTickLabels 関数は省略)
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

// (loadSeries 関数は省略)
async function loadSeries(years = 10) {
  const url = `/api/series/?ticker=${encodeURIComponent(ticker)}&frame=${frame}&years=${years}`;
  const status = document.getElementById("status");
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { "Accept": "application/json" },
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const j = await res.json();
    series = j.rows;

    const titleEl = document.getElementById("titleName");
    if(titleEl) titleEl.textContent = `（${j.name} / ${j.ticker}）`;
    
    if(status) status.textContent = `取得: ${series.length}本 / ${j.ticker} / ${frame}`;
  } catch (e) {
    console.error("loadSeries Error:", e);
    if(status) status.textContent = "データ取得に失敗: " + e.message;
    series = [];
    const titleEl = document.getElementById("titleName");
    if(titleEl) titleEl.textContent = "";
  }
}

// (drawChart 関数は省略)
function drawChart(predClose = null) {
  if (!series || series.length === 0) return;

  const close = series.map(r => r.c);
  const labels = series.map(r => r.t || ""); 

  const datasets = [{
    label: "終値",
    data: close,
    borderColor: "#198754", 
    borderWidth: 2,
    tension: 0.2,
    pointRadius: 0
  }];

  if (predClose != null && close.length) {
    datasets.push({
      label: "予測",
      data: [...Array(close.length - 1).fill(null), close.at(-1), predClose],
      borderColor: "#ffc107", 
      borderDash: [6, 4],
      borderWidth: 2,
      pointRadius: 4
    });
  }

  const ctx = document.getElementById("chart");
  if(!ctx) return; 

  if (chart) chart.destroy();
  
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.1)" },
          ticks: { color: "#adb5bd", maxTicksLimit: 12 }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.1)" },
          ticks: { color: "#adb5bd" }
        }
      }
    }
  });
}

// この関数でサーバーと通信し、予測データ(JSON)を受け取って画面を更新します
async function loadPredict() {
  const url = `/api/predict/?ticker=${encodeURIComponent(ticker)}&frame=${frame}&years=10&horizon=${horizon}`;
  const status = document.getElementById("status");

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { "Accept": "application/json" },
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const j = await res.json();

    // ★★★ デバッグログ 1: サーバーから届いた生データをコンソールに表示 ★★★
    console.log("--- loadPredict START ---");
    console.log("予測APIレスポンス (JSON):", j);
    console.log("Expected Value:", j.expected_value, "Probability:", j.probability);


    // DOM要素の取得と存在チェック
    const elLast = document.getElementById("last");
    const elAsof = document.getElementById("asof");
    const elPred = document.getElementById("pred");
    const elProb = document.getElementById("prob");
    const elModel = document.getElementById("model");
    
    // ★★★ デバッグログ 2: DOM要素の存在チェック ★★★
    if (!elLast || !elPred || !elProb) {
        console.error("【DOM ERROR】HTML要素のID（last, pred, probなど）が見つかりません。HTMLファイルを確認してください。");
    }

    // 値の反映
    if(j.name && document.getElementById("titleName")) {
        document.getElementById("titleName").textContent = `（${j.name} / ${j.ticker}）`;
    }

    if(elLast) elLast.textContent = fmt(j.close, 2);
    if(elAsof) elAsof.textContent = j.asof || "--";
    if(elPred) elPred.textContent = fmt(j.expected_value, 2);
    if(elProb) elProb.textContent = fmtP(j.probability);
    if(elModel) elModel.textContent = j.model || "--";
    
    // ★★★ デバッグログ 3: 反映後の最終値を確認 ★★★
    console.log("UI Updated: Close=", elLast?.textContent, "Pred=", elPred?.textContent);
    console.log("--- loadPredict END ---");


    // チャート描画
    drawChart(j.expected_value);

  } catch (e) {
    console.error("loadPredict Error (Catch Block):", e);
    if(status) status.textContent = "予測取得に失敗: " + e.message;
    drawChart(null);
  }
}

async function refreshAll() {
  const btn = document.getElementById("searchBtn");
  if(btn) btn.disabled = true;
  
  const status = document.getElementById("status");
  if(status) status.textContent = "データを読み込んでいます...";
  
  // ★★★ デバッグログ 4: 処理開始を確認 ★★★
  console.log("--- refreshAll START ---");

  // シリーズ取得 → 予測取得 の順で実行
  await loadSeries();
  await loadPredict();

  if(btn) btn.disabled = false;
  console.log("--- refreshAll END ---");
}

// UI handlers (イベントハンドラ部分は省略)
const searchBtn = document.getElementById("searchBtn");
if(searchBtn) searchBtn.addEventListener("click", refreshAll);

const tickerInput = document.getElementById("tickerInput");
if(tickerInput) {
    tickerInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") refreshAll();
    });
    tickerInput.addEventListener("change", (e) => {
        ticker = e.target.value.trim();
    });
}

const frameInput = document.getElementById("frame");
if(frameInput) {
    frameInput.addEventListener("change", (e) => {
        frame = e.target.value;
    });
}

const horizonInput = document.getElementById("horizon");
if(horizonInput) {
    horizonInput.addEventListener("change", (e) => {
        horizon = Number(e.target.value);
    });
}

// 初期起動
(async function boot() {
  await refreshAll();
})();