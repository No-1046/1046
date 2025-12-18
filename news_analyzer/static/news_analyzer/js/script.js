/* static/stock_analyzer/js/script.js */

// ==========================================
// 0. 定数・グローバル変数
// ==========================================
const API_BASE = "/news";
let lastDailyDates = []; // チャートの日付保持用

// ==========================================
// 1. 基本ヘルパー関数
// ==========================================
const $ = id => document.getElementById(id);
const j = obj => JSON.stringify(obj, null, 2);

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function setLoading(active, msg="処理中...") {
  const ind = $("statusIndicator");
  if(!ind) return; // 要素がないページ対策
  if(active){
      ind.className = "badge bg-warning text-dark";
      ind.textContent = "⏳ " + msg;
  } else {
      ind.className = "badge bg-secondary";
      ind.textContent = "待機中";
  }
}

function log(text, isError=false) {
  const out = $("result");
  if(!out) return; // 要素がないページ対策
  if (isError) {
      out.innerHTML += `\n<span class="text-danger">❌ ${text}</span>`;
  } else {
      out.textContent += "\n" + text;
  }
  out.scrollTop = out.scrollHeight;
}

function clearLog() {
  if($("result")) $("result").textContent = "--- 開始 ---";
}

// ==========================================
// 2. API通信関数 (GET / POST)
// ==========================================

// POST用 (収集・分析実行など)
async function postAPI(url, payload) {
  const csrftoken = getCookie('csrftoken');
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        "X-CSRFToken": csrftoken
      },
      body: JSON.stringify(payload)
    });
    if(!res.ok) {
       const txt = await res.text();
       throw new Error(`Server Error (${res.status}): ${txt}`);
    }
    return await res.json();
  } catch(e) {
    throw e;
  }
}

// GET用 (データ取得など)
async function fetchJSONEx(endpoint, params={}){
  // endpointが "/news" で始まっていない場合は付与
  let urlStr = endpoint.startsWith(API_BASE) ? endpoint : API_BASE + endpoint;
  // 完全なURLオブジェクトを作成
  const url = new URL(urlStr, window.location.origin);
  
  Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));
  return fetch(url).then(res => res.json());
}

// ==========================================
// 3. 管理画面用機能 (Crawl / Analyze)
// ==========================================
async function runCrawl() {
  const company = $("paramCompany").value;
  const ticker  = $("paramTicker").value;
  const days    = parseInt($("paramDays").value);
  if(!company || !ticker) { alert("会社名とTickerは必須です"); return; }
  
  clearLog();
  setLoading(true, "収集中...");
  log(`[Crawl] 開始: ${company} (${ticker}), 過去${days}日分`);

  try {
    const res = await postAPI("/news/crawl", { company, ticker, days });
    log(`[Done] ${res.message}`);
    log(j(res));
  } catch(e) {
    log(e.message, true);
  } finally {
    setLoading(false);
  }
}

async function runAnalyze() {
  const company = $("paramCompany").value;
  const ticker  = $("paramTicker").value;
  if(!company || !ticker) { alert("会社名とTickerは必須です"); return; }
  
  clearLog();
  setLoading(true, "分析中(数分かかります)...");
  log(`[Analyze] 開始: ${company} (${ticker}) \n※Gemini APIを使用するため時間がかかります。`);

  try {
    const res = await postAPI("/news/analyze", { company, ticker });
    log(`[Done] ${res.message}`);
    log(j(res));
  } catch(e) {
    log(e.message, true);
  } finally {
    setLoading(false);
  }
}

async function listCompanies() {
    const out = $("diagResult");
    if(!out) return;
    out.textContent = "読み込み中...";
    try {
        const res = await fetch("/news/list-companies");
        const data = await res.json();
        out.textContent = "登録済みフォルダ:\n" + j(data);
    } catch(e) {
        out.textContent = "Error: " + e;
    }
}

async function showDiag() {
    const out = $("diagResult");
    if(!out) return;
    out.textContent = "診断中...";
    try {
        const res = await fetch("/news/diag");
        const data = await res.json();
        out.textContent = "環境変数/パス診断:\n" + j(data);
    } catch(e) {
        out.textContent = "Error: " + e;
    }
}

// ==========================================
// 4. ダッシュボード画面用機能 (Chart / News)
// ==========================================

// ダッシュボード初期化
async function initCompanyList(){
    const sel = $("companySelect");
    if(!sel) return; // ダッシュボード画面でない場合は終了

    try {
      const data = await fetchJSONEx("/list-companies");
      sel.innerHTML = "";
      
      if(!data.companies || data.companies.length === 0){
        sel.innerHTML = "<option value=''>データなし</option>";
        return;
      }

      data.companies.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        sel.appendChild(opt);
      });
      // 最初の1つを自動選択して描画
      loadSelectedCompany();
    } catch(e) {
      console.error(e);
      sel.innerHTML = "<option>読み込みエラー</option>";
    }
}

// 会社選択時の処理
async function loadSelectedCompany(){
    const val = $("companySelect").value;
    if(!val) return;
    
    // "Name-Ticker" を分解
    const parts = val.split("-");
    const tickerRaw = parts.pop(); 
    let company = parts.join("-");
    if (company) {
        // nintendo → Nintendo に変換
        company = company.charAt(0).toUpperCase() + company.slice(1);
    }
    
    await updateChart(company, tickerRaw);
}

// チャート更新
async function updateChart(company, ticker){
    if(!$("chart")) return;

    // 1. データを取得
    console.log(`[Fetch] /daily 取得開始: ${company}-${ticker}`);
    const res = await fetchJSONEx("/daily", { company, ticker, days: 60 });

    // ★可視化ポイント1: 届いた生データをコンソールに全表示
    console.log("[Fetch] サーバーからの応答データ:", res);

    // 2. エラーハンドリングの細分化
    if (res.error) {
       console.error("サーバーエラー:", res.error);
       alert(`サーバーエラーが発生しました:\n${res.error}`);
       return;
    }

    // 3. データ構造のチェックと変換
    let data = [];

    if (res.daily) {
        // パターンA: 期待通りの形式 (res.dailyがある)
        console.log("データ形式: 標準 (res.daily)");
        data = res.daily;
    } 
    else if (res.dates && res.scores) {
        // パターンB: 今回のケース (res.dates, res.scores がある)
        console.warn("データ形式: 別形式 (dates/scores) を検出しました。変換します。");
        
        // バラバの配列を、JSが使いやすい「行ごとのオブジェクト」に変換
        for(let i = 0; i < res.dates.length; i++) {
            data.push({
                tradedate: res.dates[i],
                avg_sent: res.scores[i],
                closeprice: 0 // ※注意: この形式だと株価が含まれていない可能性があります
            });
        }
    } 
    else {
        // パターンC: 本当にデータがない、または全く違う形式
        console.error("データ形式不明。含まれているキー:", Object.keys(res));
        alert("データの取得に成功しましたが、形式が不明です。\nF12キーでConsoleを確認してください。");
        return;
    }

    // データが0件の場合
    if (data.length === 0) {
        alert("データが見つかりませんでした (0件)");
        return;
    }

    // ここから先は data 変数を使うので共通処理になります
    console.log(`描画対象データ: ${data.length}件`);

    // 日付セレクトボックスの更新
    const dateSel = $("dateSelect");
    const currentPick = dateSel.value;
    dateSel.innerHTML = "";
    lastDailyDates = [];
    
    data.forEach(r => {
      lastDailyDates.push(r.tradedate);
      const opt = document.createElement("option");
      opt.value = r.tradedate;
      opt.textContent = r.tradedate;
      dateSel.appendChild(opt);
    });

    if(currentPick && lastDailyDates.includes(currentPick)){
       dateSel.value = currentPick;
    } else if (lastDailyDates.length > 0) {
       dateSel.value = lastDailyDates[lastDailyDates.length - 1];
    }
    
    dateSel.onchange = () => updateHeadlines(company, ticker);

    // Plotly描画
    const dates = data.map(d => d.tradedate);
    // 株価がない場合(0)は表示がおかしくなるので注意
    const prices = data.map(d => d.closeprice || 0); 
    const sents = data.map(d => d.avg_sent);

    const trace1 = {
      x: dates, y: prices,
      name: '株価', type: 'scatter', mode: 'lines', line: {color: '#0e68ff'},
      yaxis: 'y1'
    };
    const trace2 = {
      x: dates, y: sents,
      name: '感情スコア(avg)', type: 'bar', marker: {color: '#10b981', opacity:0.6},
      yaxis: 'y2'
    };

    const layout = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#e2e8f0' },
      margin: { l: 50, r: 50, t: 30, b: 50 },
      showlegend: true,
      legend: { orientation: 'h', y: 1.1 },
      xaxis: { gridcolor: '#334155' },
      yaxis: { title: '株価', side: 'left', gridcolor: '#334155' },
      yaxis2: {
        title: '感情スコア', side: 'right', overlaying: 'y',
        range: [-1, 1], showgrid: false
      }
    };

    Plotly.newPlot('chart', [trace2, trace1], layout, {responsive: true});
    
    updateHeadlines(company, ticker);
}

// ニュース（ヘッドライン）更新 ★ここを最新版にしました
async function updateHeadlines(company, ticker){
    const headlinesDiv = $("headlines");
    const dateSel = $("dateSelect");
    let date = dateSel.value;
    
    if(!date) return;

    // ローディング表示
    headlinesDiv.innerHTML = '<div class="text-center text-muted mt-3"><div class="spinner-border spinner-border-sm text-primary" role="status"></div> AI分析結果を読み込み中...</div>';

    const hdRes = await fetchJSONEx("/headlines", { company, ticker, date });
    if (!hdRes.data) {
      headlinesDiv.innerHTML = `<div class="alert alert-secondary small">この日のニュースデータはありません</div>`;
      return;
    }

    const posArr = hdRes.data.pos || [];
    const negArr = hdRes.data.neg || [];

    // リスト生成関数
    const makeList = (arr, isPos) => {
        if(!arr.length) return '<div class="small text-muted fst-italic mb-2 ps-2">なし</div>';
        
        const icon = isPos ? "📈" : "📉";
        const borderColor = isPos ? "#198754" : "#dc3545"; // 緑 or 赤

        return arr.map(r => {
            const title = r.title || r.newstitle;
            const url = r.url || r.newslink;
            const score = Number(r.sentimentscore).toFixed(2);
            const reason = r.reason || "AIによる理由なし";

            return `
            <a href="${url}" target="_blank" 
               class="btn btn-outline-dark text-start w-100 mb-2 position-relative text-light border-secondary"
               style="border-left: 5px solid ${borderColor}; background-color: #212529;"
               title="${reason}">
              <div class="d-flex w-100 justify-content-between align-items-center">
                <span class="fw-bold text-truncate me-2" style="font-size:0.9rem;">${title}</span>
                <span class="badge ${isPos ? 'bg-success' : 'bg-danger'}">${icon} ${score}</span>
              </div>
              <div class="small text-secondary mt-1 text-truncate" style="font-size: 0.75rem;">
                🤖 ${reason}
              </div>
            </a>
        `}).join("");
    };

    let html = "";
    html += `<h6 class="text-success small fw-bold mb-2"><i class="bi bi-emoji-smile"></i> ポジティブ要因</h6>`;
    html += `<div class="mb-4">${makeList(posArr, true)}</div>`;
    
    html += `<h6 class="text-danger small fw-bold mb-2"><i class="bi bi-emoji-frown"></i> ネガティブ要因</h6>`;
    html += `<div>${makeList(negArr, false)}</div>`;

    headlinesDiv.innerHTML = html;
}

// ==========================================
// 5. 起動時処理
// ==========================================
window.addEventListener("DOMContentLoaded", async () => {
  // ダッシュボード画面なら会社リスト読み込みを開始
  if($("companySelect")) {
      await initCompanyList();
  }
});