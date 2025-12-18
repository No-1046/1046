import os
import sys
import json
import glob
import subprocess
import pandas as pd
import numpy as np

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
    ダッシュボード用: 完全デバッグ版
    """
    import traceback # エラー詳細を見るために追加

    raw_ticker = request.GET.get('ticker', '7974') 
    search_key = raw_ticker.lower().replace('t', '').replace('.', '')
    
    print(f"\n=== api_daily START: {raw_ticker} (Key: {search_key}) ===")

    # 1. フォルダ検索
    base_dir = os.path.join(settings.BASE_DIR, 'companies')
    target_dir = None
    
    if os.path.exists(base_dir):
        for d in os.listdir(base_dir):
            if search_key in d:
                target_dir = os.path.join(base_dir, d, 'history_csv')
                if os.path.exists(target_dir):
                    break
    
    if not target_dir:
        print("!!! Error: フォルダが見つかりません")
        return JsonResponse({"dates": [], "scores": [], "counts": []})

    print(f"Target Dir: {target_dir}")

    # 2. ファイル検索
    csv_files = glob.glob(os.path.join(target_dir, "history_append_*.csv"))
    csv_files.sort()
    print(f"Found {len(csv_files)} CSV files.")
    
    data_list = []

    # 3. ファイル読み込みループ（ここを詳細にログ出力）
    for f in csv_files:
        fname = os.path.basename(f)
        print(f"--- Processing: {fname} ---")
        
        try:
            # ファイルサイズチェック
            if os.path.getsize(f) == 0:
                print("  > SKIPPED: File size is 0 bytes (Empty file)")
                continue

            # 日付抽出
            date_part = fname.replace("history_append_", "").replace(".csv", "")
            if len(date_part) == 8:
                date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"
            else:
                date_str = date_part
            print(f"  > Date extracted: {date_str}")

            # CSV読み込み
            df = pd.read_csv(f, encoding='utf-8-sig')
            print(f"  > CSV Loaded. Shape: {df.shape}")
            print(f"  > Columns: {list(df.columns)}")

            # 列名チェック
            score_col = None
            for col in df.columns:
                if "score" in col.lower() or "sentiment" in col.lower():
                    score_col = col
                    break
            
            if score_col:
                avg_score = df[score_col].mean()
                count = len(df)
                print(f"  > OK: Col='{score_col}', Avg={avg_score}, Count={count}")
            else:
                avg_score = 0
                count = 0
                print("  > WARNING: Score column not found. Set to 0.")

            data_list.append({
                "date": date_str,
                "score": 0 if pd.isna(avg_score) else avg_score,
                "count": count
            })
            print("  > Append Success!")

        except Exception as e:
            print(f"  > !!! ERROR reading file: {e}")
            # エラーの詳細を表示
            traceback.print_exc()
            continue

    print(f"=== api_daily END: Returning {len(data_list)} items ===\n")

    return JsonResponse({
        "dates": [d["date"] for d in data_list],
        "scores": [d["score"] for d in data_list],
        "counts": [d["count"] for d in data_list]
    })
    

def api_forecast(request):
    """
    [GET] 最新の予測データを取得して返す
    Query: ?company=...&ticker=...
    """
    company = request.GET.get("company")
    ticker = request.GET.get("ticker")
    
    base_path = _get_company_dir(company, ticker)
    if not base_path:
        return JsonResponse({"error": "パラメータ不足"}, status=400)
        
    result = _read_latest_forecast(base_path)
    return JsonResponse({"forecast": result})

def api_headlines(request):
    """
    ダッシュボード用: ニュース詳細取得 (フォルダ検索強化版)
    """
    # 1. パラメータ取得と検索キー生成
    raw_ticker = request.GET.get('ticker', '7974')
    date_str = request.GET.get('date')
    
    # "7974t" -> "7974" に変換して探す
    search_key = raw_ticker.lower().replace('t', '').replace('.', '')
    
    print(f"--- api_headlines: {raw_ticker} (Key: {search_key}, Date: {date_str}) ---")

    if not date_str:
        return JsonResponse({"error": "日付指定が必要です"}, status=400)

    # 2. フォルダを探す
    base_dir = os.path.join(settings.BASE_DIR, 'companies')
    target_dir = None
    
    if os.path.exists(base_dir):
        for d in os.listdir(base_dir):
            if search_key in d:
                path_candidate = os.path.join(base_dir, d, 'history_csv')
                if os.path.exists(path_candidate):
                    target_dir = path_candidate
                    break
    
    if not target_dir:
        print("Error: フォルダが見つかりません")
        return JsonResponse({"data": {"pos": [], "neg": []}})

    # 3. CSVファイルパスの特定
    date_clean = date_str.replace("-", "")
    csv_name = f"history_append_{date_clean}.csv"
    csv_path = os.path.join(target_dir, csv_name)
    
    if not os.path.exists(csv_path):
        print(f"Error: ファイルなし {csv_path}")
        return JsonResponse({"data": {"pos": [], "neg": []}})

    # 4. CSV読み込み
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        
        # 列名ゆらぎ吸収
        score_col = "sentimentscore"
        for col in df.columns:
            if "score" in col.lower() or "sentiment" in col.lower():
                score_col = col
                break

        # データ整形
        if score_col in df.columns:
            df[score_col] = pd.to_numeric(df[score_col], errors='coerce').fillna(0)
            df = df.sort_values(score_col)
        else:
            # スコア列がない場合は全部0扱いでリストだけ出す
            df["dummy_score"] = 0
            score_col = "dummy_score"

        df = df.fillna("") # 空文字埋め

        neg_df = df.head(5)
        pos_df = df.tail(5).iloc[::-1]
        
        return JsonResponse({
            "data": {
                "pos": pos_df.to_dict(orient="records"),
                "neg": neg_df.to_dict(orient="records")
            }
        })
        
    except Exception as e:
        print(f"Error in api_headlines: {e}")
        return JsonResponse({"error": str(e)}, status=500)