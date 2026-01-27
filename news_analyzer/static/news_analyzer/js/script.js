/* static/stock_analyzer/js/script.js */

// ==========================================
// 0. 定数・グローバル変数
// ==========================================
const API_BASE = "/news";
let lastDailyDates = []; // チャートの日付保持用
let currentCompanyName = ""; // 取得した会社名を保持

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

// 会社名表示
function showCompanyName(companyName) {
  currentCompanyName = companyName;
  const displayDiv = $("companyNameDisplay");
  const nameSpan = $("detectedCompanyName");
  if (displayDiv && nameSpan) {
    nameSpan.textContent = companyName;
    displayDiv.style.display = 'block';
  }
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
  const ticker = $("paramTicker").value.trim();
  const days = parseInt($("paramDays").value);
  
  if(!ticker) { 
    alert("銘柄コードを入力してください"); 
    return; 
  }
  
  clearLog();
  setLoading(true, "収集中...");
  log(`[Crawl] 開始: ${ticker}, 過去${days}日分`);

  try {
    // company パラメータを削除、ticker のみ送信
    const res = await postAPI("/news/crawl", { ticker, days });
    
    // 会社名が返ってきたら表示
    if (res.company_name) {
      showCompanyName(res.company_name);
      log(`[会社名] ${res.company_name}`);
    }
    
    log(`[Done] ${res.message}`);
    log(j(res));
  } catch(e) {
    log(e.message, true);
  } finally {
    setLoading(false);
  }
}

async function runAnalyze() {
  const ticker = $("paramTicker").value.trim();
  
  if(!ticker) { 
    alert("銘柄コードを入力してください"); 
    return; 
  }
  
  clearLog();
  setLoading(true, "分析中...");
  log(`[Analyze] 開始: ${ticker} \n※Gemini APIを使用するため時間がかかります。`);

  try {
    // company パラメータを削除、ticker のみ送信
    const res = await postAPI("/news/analyze", { ticker });
    
    // 会社名が返ってきたら表示
    if (res.company_name) {
      showCompanyName(res.company_name);
      log(`[会社名] ${res.company_name}`);
    }
    
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
    const ticker = $("companySelect").value;
    if(!ticker) return;
    
    await updateChart(ticker);  // company パラメータを削除
}

// チャート更新    
async function updateChart(ticker){
    if(!$("chart")) return;

    console.log(`[Fetch] /daily 取得開始: ticker=${ticker}`);
    const res = await fetchJSONEx("/daily", { ticker: ticker });
    console.log("[Fetch] サーバーからの応答データ:", res);

    if (res.error) {
       console.error("サーバーエラー:", res.error);
       alert(`サーバーエラーが発生しました:\n${res.error}`);
       return;
    }

    let data = [];
    
    if (res.daily && Array.isArray(res.daily)) {
        data = res.daily;
        console.log(`データ形式: 標準 (res.daily) - ${data.length}件`);
    } else {
        console.error("データ形式不明。含まれているキー:", Object.keys(res));
        alert("データの取得に成功しましたが、形式が不明です。");
        return;
    }

    if (data.length === 0) {
        alert("データが見つかりませんでした (0件)");
        return;
    }

    console.log(`描画対象データ: ${data.length}件`);

    // 感情データがある日付のみをセレクトボックスに追加
    const dateSel = $("dateSelect");
    const currentPick = dateSel.value;
    dateSel.innerHTML = "";
    lastDailyDates = [];
    
    data.forEach(r => {
      // has_sentiment が true の日付のみ追加
      if (r.has_sentiment) {
        const dateVal = r.date || r.tradedate;
        lastDailyDates.push(dateVal);
        const opt = document.createElement("option");
        opt.value = dateVal;
        opt.textContent = dateVal;
        dateSel.appendChild(opt);
      }
    });

    // セレクトボックスが空の場合の処理
    if (lastDailyDates.length === 0) {
        dateSel.innerHTML = '<option value="">(ニュース分析データなし)</option>';
        console.warn("ニュース分析済みの日付が見つかりませんでした");
    } else {
        // 以前選択していた日付を維持、なければ最新日を選択
        if(currentPick && lastDailyDates.includes(currentPick)){
           dateSel.value = currentPick;
        } else {
           dateSel.value = lastDailyDates[lastDailyDates.length - 1];
        }
    }
    
    dateSel.onchange = () => updateHeadlines(ticker);

    // グラフ用配列作成
    const dates  = data.map(d => d.date || d.tradedate);
    const prices = data.map(d => d.price || d.closeprice || 0);
    const sents  = data.map(d => d.sentiment || d.avg_sent || 0);
    
    // 感情データがある日のみの情報を抽出（マーカー表示用）
    const sentimentDates = data.filter(d => d.has_sentiment).map(d => d.date);
    const sentimentPrices = data.filter(d => d.has_sentiment).map(d => d.price);

    // Trace1: 株価ライン（全期間）
    const trace1 = {
      x: dates, 
      y: prices,
      name: '株価',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#0e68ff', width: 2 },
      yaxis: 'y1'
    };
    
    // Trace2: 感情データがある日のマーカー
    const trace2 = {
      x: sentimentDates,
      y: sentimentPrices,
      name: 'ニュース分析済み',
      type: 'scatter',
      mode: 'markers',
      marker: { 
        color: '#10b981', 
        size: 8,
        symbol: 'circle'
      },
      yaxis: 'y1',
      hovertemplate: '%{x}<br>株価: %{y:.2f}円<extra></extra>'
    };

    // Trace3: 感情スコア（バー）- 分析済みの日のみ表示
    const trace3 = {
      x: sentimentDates, 
      y: data.filter(d => d.has_sentiment).map(d => d.sentiment),
      name: '感情スコア',
      type: 'bar',
      marker: { 
        color: data.filter(d => d.has_sentiment).map(d => {
          const s = d.sentiment;
          return s > 0 ? '#10b981' : s < 0 ? '#ef4444' : '#6b7280';
        }),
        opacity: 0.6 
      },
      yaxis: 'y2',
      hovertemplate: '%{x}<br>スコア: %{y:.3f}<extra></extra>'
    };

    // Layout
    const layout = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#e2e8f0' },
      margin: { l: 60, r: 60, t: 30, b: 50 },
      showlegend: true,
      legend: { 
        orientation: 'h', 
        y: 1.15,
        x: 0.5,
        xanchor: 'center'
      },
      xaxis: { 
        gridcolor: '#334155',
        title: '日付'
      },
      yaxis: { 
        title: '株価 (円)', 
        side: 'left', 
        gridcolor: '#334155',
        titlefont: { color: '#0e68ff' },
        tickfont: { color: '#0e68ff' }
      },
      yaxis2: {
        title: '感情スコア',
        side: 'right',
        overlaying: 'y',
        range: [-1, 1],
        showgrid: false,
        titlefont: { color: '#10b981' },
        tickfont: { color: '#10b981' },
        zeroline: true,
        zerolinecolor: '#6b7280',
        zerolinewidth: 1
      },
      hovermode: 'x unified'
    };

    // 描画（順序: バー→ライン→マーカー）
    Plotly.newPlot('chart', [trace3, trace1, trace2], layout, { responsive: true });
    
    // 初回表示時に自動的にニュースを読み込む
    if (lastDailyDates.length > 0) {
        updateHeadlines(ticker);
    }
}

async function updateHeadlines(ticker){
    const headlinesDiv = $("headlines");
    const dateSel = $("dateSelect");
    let date = dateSel.value;
    
    if(!date) return;

    headlinesDiv.innerHTML = '<div class="text-center text-muted mt-3"><div class="spinner-border spinner-border-sm text-primary" role="status"></div> AI分析結果を読み込み中...</div>';

    const hdRes = await fetchJSONEx("/headlines", { ticker, date });  
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