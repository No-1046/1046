import os
import sys
import json
import glob
import re
import subprocess
import pandas as pd
import numpy as np
import yfinance as yf

from django.shortcuts import render
from django.http import JsonResponse, HttpResponseBadRequest
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

# ==========================================
# 設定・定数定義
# ==========================================

# 実行するスクリプトがあるディレクトリ (news_analyzer/scripts/ を想定)
SCRIPTS_DIR = os.path.join(settings.BASE_DIR, 'news_analyzer', 'scripts')

# データを保存するディレクトリ (プロジェクトルート/companies/ を作成して使用)
COMPANIES_DIR = os.path.join(settings.BASE_DIR, 'news_analyzer/companies')

# Pythonの実行コマンド (現在の仮想環境のPythonを使う)
PYTHON_EXE = sys.executable

# ==========================================
# ヘルパー関数
# ==========================================

def _normalize_ticker(raw: str) -> str:
    """
    銘柄コードを正規化する
    例: "7974" -> "7974.T"
    """
    if not raw:
        return ""
    raw = str(raw).strip().upper()
    # 日本株（数字4桁）の場合、末尾に .T を付与
    import re
    if re.match(r"^\d{4}$", raw):
        return f"{raw}.T"
    return raw

def _get_company_dir(company: str, ticker: str) -> str:
    """
    会社名とティッカーから、データを保存するフォルダパスを生成する
    例: .../companies/Nintendo-7974t
    """
    if not company or not ticker:
        return None
    
    ticker_norm = _normalize_ticker(ticker)
    # フォルダ名に使用できない文字を置換するなど、簡易的なサニタイズ
    safe_company = company.replace(" ", "_").replace("/", "_")
    safe_ticker = ticker_norm.lower().replace(".", "")
    
    folder_name = f"{safe_company}-{safe_ticker}"
    return os.path.join(COMPANIES_DIR, folder_name)

def _read_latest_forecast(base_dir: str):
    """
    指定フォルダ内の最新の forecast_*.csv を読み込む
    """
    hist_dir = os.path.join(base_dir, "history_csv")
    if not os.path.exists(hist_dir):
        return None
        
    files = glob.glob(os.path.join(hist_dir, "forecast_*.csv"))
    if not files:
        return None
        
    # 作成日時順ではなく、ファイル名のタイムスタンプ等でソート推奨だが、
    # ここではファイルの更新日時(getmtime)で最新を取得
    latest_file = max(files, key=os.path.getmtime)
    
    try:
        df = pd.read_csv(latest_file)
        # JSON化のためNaNをNoneに変換
        return df.where(pd.notnull(df), None).to_dict(orient="records")
    except Exception as e:
        print(f"Error reading forecast: {e}")
        return None

# ==========================================
# View関数 (画面表示)
# ==========================================

def index(request):
    """トップページ (検索・実行画面)"""
    return render(request, 'news_analyzer/index.html')

def dashboard(request):
    """ダッシュボード (分析結果表示画面)"""
    return render(request, 'news_analyzer/dashboard.html')

# ==========================================
# API View関数 (JSON応答)
# ==========================================

def api_list_companies(request):
    """作成済みの会社データフォルダ一覧を返す"""
    if not os.path.exists(COMPANIES_DIR):
        return JsonResponse({"companies": []})
    
    # companiesディレクトリ直下のフォルダ名を取得
    dirs = [d for d in os.listdir(COMPANIES_DIR) 
            if os.path.isdir(os.path.join(COMPANIES_DIR, d))]
    
    return JsonResponse({"companies": dirs})

def api_diag(request):
    """システム診断情報を返す"""
    api_key = os.environ.get("GEMINI_API_KEY")
    return JsonResponse({
        "status": "ok",
        "python_path": PYTHON_EXE,
        "base_dir": str(settings.BASE_DIR),
        "scripts_dir": str(SCRIPTS_DIR),
        "companies_dir": str(COMPANIES_DIR),
        "gemini_api_key_set": bool(api_key), # キーが設定されているか
    })

@csrf_exempt
def api_crawl(request):
    """
    [POST] ニュースクローラーを実行する
    JSON body: { "company":Str, "ticker":Str, "days":Int }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST method required")
    
    try:
        # JSONデータの取得
        data = json.loads(request.body)
        company = data.get("company")
        ticker = data.get("ticker")
        days = data.get("days", 3)
        
        if not company or not ticker:
            return JsonResponse({"error": "会社名と銘柄コードは必須です"}, status=400)
            
        ticker_norm = _normalize_ticker(ticker)
        
        # 保存先ディレクトリの準備
        target_dir = _get_company_dir(company, ticker)
        os.makedirs(target_dir, exist_ok=True)
        
        # スクリプトのパス
        script_path = os.path.join(SCRIPTS_DIR, 'news_crawler_mvp.py')
        if not os.path.exists(script_path):
            return JsonResponse({"error": f"Script not found: {script_path}"}, status=500)

        # コマンド作成
        cmd = [
            PYTHON_EXE, script_path,
            "--company", company,
            "--ticker", ticker_norm,
            "--last-ndays", str(days),
            # 必要に応じて他の引数も追加
        ]
        
        # 環境変数の設定 (クローラーは環境変数 NIN_PROJECT_BASE を見て保存先を決める仕様と仮定)
        env = os.environ.copy()
        env["NIN_PROJECT_BASE"] = target_dir
        
        # 実行 (cwdはBASE_DIRにしておく)
        subprocess.run(cmd, env=env, check=True, cwd=settings.BASE_DIR)
        
        return JsonResponse({"status": "ok", "message": "クローリングが完了しました"})

    except subprocess.CalledProcessError as e:
        return JsonResponse({"error": f"実行エラー: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"システムエラー: {str(e)}"}, status=500)

@csrf_exempt
def api_analyze(request):
    """
    [POST] 分析パイプラインを実行する
    JSON body: { "company":Str, "ticker":Str }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST method required")

    try:
        data = json.loads(request.body)
        company = data.get("company")
        ticker = data.get("ticker")
        
        if not company or not ticker:
            return JsonResponse({"error": "会社名と銘柄コードは必須です"}, status=400)
            
        # ターゲットディレクトリ
        base_path = _get_company_dir(company, ticker)
        if not base_path or not os.path.exists(base_path):
             return JsonResponse({"error": "データフォルダが見つかりません。先にクローリングを行ってください。"}, status=404)
        
        # today_csv の場所 (入力)
        input_csv_dir = os.path.join(base_path, "today_csv")
        
        script_path = os.path.join(SCRIPTS_DIR, 'local_pipeline_run.py')
        if not os.path.exists(script_path):
            return JsonResponse({"error": f"Script not found: {script_path}"}, status=500)

        # コマンド作成
        cmd = [
            PYTHON_EXE, script_path,
            "--input", input_csv_dir,
            "--base", base_path, # 出力先はこのbaseの下の history_csv になる
            "--use-gemini",
            "--filter-lowimpact"
        ]
        
        # 環境変数でターゲット情報を渡す
        env = os.environ.copy()
        env["TARGET_COMPANY"] = company
        env["TARGET_TICKER"] = _normalize_ticker(ticker)
        # GEMINI_API_KEY が環境変数にあることが前提
        
        subprocess.run(cmd, env=env, check=True, cwd=settings.BASE_DIR)
        
        return JsonResponse({"status": "ok", "message": "分析が完了しました"})

    except subprocess.CalledProcessError as e:
        return JsonResponse({"error": f"分析実行エラー: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"システムエラー: {str(e)}"}, status=500)

# views.py に以下の import があるか確認してください（なければ上部に追加）
import os
import glob
import pandas as pd
from django.http import JsonResponse
from django.conf import settings

# ... 他の関数の下に追加 ...

def api_daily(request):
    """
    ダッシュボード用: 株価データ(yfinance) + 感情スコア(CSV)
    新旧両方のデータ形式に対応
    """
    import traceback
    
    raw_ticker = request.GET.get('ticker', '7974')
    search_key = raw_ticker.lower().replace('t', '').replace('.', '')
    
    print(f"\n=== api_daily START: {raw_ticker} (Key: {search_key}) ===")
    
    # 1. フォルダ検索（大文字小文字を区別しない）
    if not os.path.exists(COMPANIES_DIR):
        print(f"!!! Error: COMPANIES_DIR が見つかりません: {COMPANIES_DIR}")
        return JsonResponse({"error": "データディレクトリが見つかりません"}, status=404)
    
    print(f"Companies Dir: {COMPANIES_DIR}")
    
    target_dir = None
    for d in os.listdir(COMPANIES_DIR):
        # 大文字小文字を区別せずに検索
        if search_key in d.lower():
            candidate = os.path.join(COMPANIES_DIR, d, 'history_csv')
            print(f"  Checking: {d} -> {candidate}")
            if os.path.exists(candidate):
                target_dir = candidate
                print(f"  ✓ Found: {target_dir}")
                break
    
    if not target_dir:
        print(f"!!! Error: フォルダが見つかりません (search_key: {search_key})")
        available = [d for d in os.listdir(COMPANIES_DIR) if os.path.isdir(os.path.join(COMPANIES_DIR, d))]
        print(f"利用可能なフォルダ: {available}")
        return JsonResponse({"error": f"データフォルダが見つかりません (ticker: {raw_ticker})"}, status=404)
    
    # 2. CSVから感情スコアを取得（柔軟な列名対応）
    csv_files = glob.glob(os.path.join(target_dir, "history_append_*.csv"))
    csv_files.sort()
    print(f"Found {len(csv_files)} CSV files.")
    
    sentiment_data = {}
    
    for f in csv_files:
        fname = os.path.basename(f)
        
        try:
            if os.path.getsize(f) == 0:
                print(f"  > SKIP: {fname} (empty)")
                continue
            
            # 日付抽出
            date_part = fname.replace("history_append_", "").replace(".csv", "")
            if len(date_part) == 8:
                date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"
            else:
                date_str = date_part
            
            df = pd.read_csv(f, encoding='utf-8-sig')
            
            # 空のDataFrameチェック
            if len(df) == 0:
                print(f"  > SKIP: {fname} (no rows)")
                continue
            
            # スコア列を探す（複数のパターンに対応）
            score_col = None
            possible_cols = ['sentimentscore', 'sentiment_score', 'score', 'sentiment']
            
            for col in df.columns:
                col_lower = col.lower().strip()
                if any(pattern in col_lower for pattern in possible_cols):
                    score_col = col
                    break
            
            if score_col and len(df) > 0:
                # 数値変換して平均を計算
                scores = pd.to_numeric(df[score_col], errors='coerce')
                avg_score = scores.mean()
                
                if not pd.isna(avg_score):
                    sentiment_data[date_str] = float(avg_score)
                    print(f"  ✓ {fname}: {date_str} -> Score: {avg_score:.3f} ({len(df)} news)")
                else:
                    print(f"  > WARN: {fname}: スコアがすべてNaN")
            else:
                print(f"  > WARN: {fname}: スコア列が見つかりません (Columns: {list(df.columns)})")
                
        except Exception as e:
            print(f"  > ERROR reading {fname}: {e}")
            continue
    
    print(f"Sentiment data collected: {len(sentiment_data)} dates")
    
    # 3. yfinanceで株価データを取得
    ticker_clean = search_key
    ticker_yf = f"{ticker_clean}.T"
    
    print(f"[yfinance] Fetching: {ticker_yf}")
    
    try:
        stock_df = yf.download(ticker_yf, period="1y", interval="1d", 
                              progress=False, auto_adjust=True)
        
        if stock_df is None or stock_df.empty:
            print("!!! yfinance returned no data")
            return JsonResponse({"error": f"株価データが取得できませんでした ({ticker_yf})"}, status=404)
        
        if stock_df.index.tz is not None:
            stock_df.index = stock_df.index.tz_localize(None)
        
        print(f"[yfinance] Got {len(stock_df)} rows")
        
    except Exception as e:
        print(f"!!! yfinance ERROR: {e}")
        traceback.print_exc()
        return JsonResponse({"error": f"株価取得エラー: {str(e)}"}, status=500)
    
    # 4. データを統合（FutureWarning修正）
    result_data = []
    
    for date_idx, row in stock_df.iterrows():
        date_str = date_idx.strftime("%Y-%m-%d")
        result_data.append({
            "date": date_str,
            "price": float(row["Close"].iloc[0]) if isinstance(row["Close"], pd.Series) else float(row["Close"]),  # ★修正
            "sentiment": sentiment_data.get(date_str, 0),
            "has_sentiment": date_str in sentiment_data
        })
    
    result_data.sort(key=lambda x: x["date"])
    
    print(f"=== api_daily END: Total {len(result_data)} items, {len(sentiment_data)} with sentiment ===\n")
    
    return JsonResponse({"daily": result_data})


def api_headlines(request):
    """
    ダッシュボード用: ニュース詳細取得（新旧データ形式対応）
    """
    raw_ticker = request.GET.get('ticker', '7974')
    date_str = request.GET.get('date')
    
    search_key = raw_ticker.lower().replace('t', '').replace('.', '')
    
    print(f"--- api_headlines: {raw_ticker} (Key: {search_key}, Date: {date_str}) ---")

    if not date_str:
        return JsonResponse({"error": "日付指定が必要です"}, status=400)

    # フォルダを探す（大文字小文字を区別しない）
    if not os.path.exists(COMPANIES_DIR):
        print(f"Error: COMPANIES_DIR が見つかりません: {COMPANIES_DIR}")
        return JsonResponse({"data": {"pos": [], "neg": []}})
    
    target_dir = None
    for d in os.listdir(COMPANIES_DIR):
        if search_key in d.lower():
            path_candidate = os.path.join(COMPANIES_DIR, d, 'history_csv')
            if os.path.exists(path_candidate):
                target_dir = path_candidate
                print(f"  ✓ Found folder: {d}")
                break
    
    if not target_dir:
        print("Error: フォルダが見つかりません")
        return JsonResponse({"data": {"pos": [], "neg": []}})

    # CSVファイルパスの特定
    date_clean = date_str.replace("-", "")
    csv_name = f"history_append_{date_clean}.csv"
    csv_path = os.path.join(target_dir, csv_name)
    
    print(f"  Looking for: {csv_path}")
    
    if not os.path.exists(csv_path):
        print(f"Error: ファイルなし {csv_path}")
        existing_files = [f for f in os.listdir(target_dir) if f.startswith("history_append_")]
        print(f"  利用可能なファイル: {existing_files[:5]}...")
        
        return JsonResponse({
            "data": {"pos": [], "neg": []},
            "message": f"指定日のデータが見つかりません ({date_str})"
        })

    # CSV読み込み（柔軟な列名対応）
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        print(f"  ✓ CSV loaded: {len(df)} rows, Columns: {list(df.columns)}")
        
        if len(df) == 0:
            return JsonResponse({
                "data": {"pos": [], "neg": []},
                "message": "データが空です"
            })
        
        # スコア列を探す（複数のパターンに対応）
        score_col = None
        possible_score_cols = ['sentimentscore', 'sentiment_score', 'score', 'sentiment']
        
        for col in df.columns:
            col_lower = col.lower().strip()
            if any(pattern in col_lower for pattern in possible_score_cols):
                score_col = col
                print(f"  ✓ Score column found: '{score_col}'")
                break
        
        if not score_col:
            print(f"  Warning: スコア列が見つかりません。")
            df["dummy_score"] = 0
            score_col = "dummy_score"
        
        # タイトル列とURL列を探す（柔軟に対応）
        title_col = None
        url_col = None
        
        for col in df.columns:
            col_lower = col.lower().strip()
            if 'title' in col_lower and not title_col:
                title_col = col
            if 'url' in col_lower or 'link' in col_lower and not url_col:
                url_col = col
        
        print(f"  Title column: {title_col}, URL column: {url_col}")

        # データ整形
        df[score_col] = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
        df = df.sort_values(score_col)
        df = df.fillna("")

        # 1. 明確にネガティブなものと、ポジティブなものに分ける (0は除外)
        neg_candidates = df[df["sentimentscore"] < 0]
        pos_candidates = df[df["sentimentscore"] > 0]

        # 2. ネガティブ候補から下位5件（スコアが低い順＝悪い順）
        neg_df = neg_candidates.nsmallest(5, "sentimentscore")
        # または neg_df = neg_candidates.head(5) # ソート済みならこれでもOK

        # 3. ポジティブ候補から上位5件（スコアが高い順＝良い順）
        pos_df = pos_candidates.nlargest(5, "sentimentscore")
        # または pos_df = pos_candidates.tail(5).iloc[::-1] # ソート済みならこれでもOK
        
        # 列名を標準化してレスポンス
        def normalize_row(row):
            return {
                "title": row.get(title_col, row.get('title', row.get('newstitle', ''))),
                "url": row.get(url_col, row.get('url', row.get('newslink', ''))),
                "sentimentscore": float(row.get(score_col, 0)),
                "reason": row.get('reason', row.get('理由', 'AIによる理由なし'))
            }
        
        pos_list = [normalize_row(row) for _, row in pos_df.iterrows()]
        neg_list = [normalize_row(row) for _, row in neg_df.iterrows()]
        
        print(f"  ✓ Returning Positive: {len(pos_list)}, Negative: {len(neg_list)}")
        
        return JsonResponse({
            "data": {
                "pos": pos_list,
                "neg": neg_list
            }
        })
        
    except Exception as e:
        print(f"Error in api_headlines: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)



    
#グラフ描画    
    
def some_feature_view(request):
    profile = getattr(request.user, "userprofile", None)
    if profile is not None:
        profile.usage_count += 1
        profile.save()    
    
def tz_naive_index(df): 
    return df.tz_localize(None) if df.index.tz is not None else df
    
def _normalize_ticker(raw: str) -> str:
    """
    銘柄コードを正規化する
    例: "7974" -> "7974.T"
        "6501t" -> "6501.T"
        "6501T" -> "6501.T"
    """
    if not raw:
        return ""
    raw = str(raw).strip().upper()
    
    # 既に .T がついている場合はそのまま返す
    if raw.endswith(".T"):
        return raw
    
    # "T" だけがついている場合は ".T" に置き換え
    if raw.endswith("T") and len(raw) > 1:
        raw = raw[:-1] + ".T"
        return raw
    
    # 日本株（数字4桁）の場合、末尾に .T を付与
    import re
    if re.match(r"^\d{4}$", raw):
        return f"{raw}.T"
    
    return raw

def fetch_ohlc(ticker: str, interval: str = "1d", years: int = 1) -> pd.DataFrame:
    period = f"{years}y"
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        try:
            df.columns = df.columns.get_level_values(0)
        except IndexError:
            pass

    return tz_naive_index(df)

def get_name_safe(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).get_info()
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker

_models = {}  

def news_series(request):
    ticker = request.GET.get('ticker', '6501')
    frame = request.GET.get('frame', '1d')
    tk = normalize_ticker(ticker)
    df = fetch_ohlc(tk, interval=frame)
    
    if df is None:
        return JsonResponse({"error": f"{ticker}: no data found"}, status=404)

    df = df[["Open", "High", "Low", "Close"]].dropna()
    name = get_name_safe(tk)

    rows = [
        {
            "t": ts.strftime("%Y-%m-%d"),
            "o": float(row["Open"]),
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
        }
        for ts, row in df.iterrows()
    ]

    some_feature_view(request)

    #return rows
    
    return JsonResponse({
        "ticker": tk,
        "name": name,
        "frame": frame,
        "rows": rows[-1200:]
    }, safe=False)