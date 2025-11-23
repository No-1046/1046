import re
import numpy as np
import pandas as pd
import yfinance as yf
import joblib
import lightgbm as lgb

from xgboost import XGBClassifier
from django.http import JsonResponse, HttpRequest
from django.shortcuts import render
from django.conf import settings
from .indicators import calculate_indicators, FEATURE_COLS



# モデルへのパス
MODEL_PATH = MODEL_PATH = settings.BASE_DIR / "stock_analyzer" / "model.pkl"


# --- 特徴量計算のダミー関数群 ---
# 本来は features.py などに記述するロジックです
def tz_naive_index(df): return df.tz_localize(None) if df.index.tz is not None else df
def last_feature_row(df): return df.iloc[[-1]]
# --- ここまでダミー関数 ---

def normalize_ticker(s: str) -> str:
    s = s.strip().upper()
    if re.fullmatch(r"\d{4}", s):
        return f"{s}.T"
    return s

def fetch_ohlc(ticker: str, interval: str = "1d", years: int = 5) -> pd.DataFrame:
    period = f"{years}y" if interval in ("1d", "1wk","1mo") else f"{max(years, 10)}y"
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True, group_by="column")
    return None if df is None or df.empty else tz_naive_index(df)

def get_name_safe(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).get_info()
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker

_model = None
def get_model():
    global _model
    if _model is not None:
        return _model

    if MODEL_PATH.exists():
        _model = joblib.load(MODEL_PATH)
        return _model

    # model.pkl が無い場合のみ、Fallbackとしてゼロ予測
    class Baseline:
        feature_names_in_ = FEATURE_COLS
        def predict_proba(self, X: pd.DataFrame):
            return np.c_[np.ones(len(X))*0.5, np.ones(len(X))*0.5]
    _model = Baseline()
    return _model


def index(request: HttpRequest):
    return render(request, 'index.html')


#システム使用回数管理
def some_feature_view(request):
    profile = getattr(request.user, "userprofile", None)

    # UserProfile が存在する場合のみ usage_count を更新
    if profile is not None:
        profile.usage_count += 1
        profile.save()
    else:
        # ログインしていない or UserProfileがない場合はスキップ
        print("UserProfile が存在しないため usage_count は更新されませんでした。")

        
def get_series(request):
    ticker = request.GET.get('ticker', '6501')
    frame = request.GET.get('frame', '1d')
    tk = normalize_ticker(ticker)
    df = fetch_ohlc(tk, interval=frame)
    if df is None:
        return JsonResponse({"error": f"{ticker}: no data found"}, status=404)

    # 欲しいカラムだけ抽出
    df = df[["Open", "High", "Low", "Close"]].dropna()
    name = get_name_safe(tk)

    # pandas.Timestamp → str, numpy.float64 → float に変換
    rows = [
        {
            "t": ts.strftime("%Y-%m-%d"),  # 日付を文字列化
            "o": float(r["Open"].iloc[0]),
            "h": float(r["High"].iloc[0]),
            "l": float(r["Low"].iloc[0]),
            "c": float(r["Close"].iloc[0]),

        }
        for ts, r in df.iterrows()
    ]

    # ユーザーの使用履歴更新（存在しない場合はスキップ）
    some_feature_view(request)

    # 安全にJSON化
    return JsonResponse({
        "ticker": tk,
        "name": name,
        "frame": frame,
        "rows": rows[-1200:]
    }, safe=False)


def get_predict(request: HttpRequest):
    print("=== Debug: get_predict start ===")  # ★開始

    # --- 1. パラメータ取得 ---
    ticker = request.GET.get('ticker', '6501')
    frame = request.GET.get('frame', '1d')
    horizon = int(request.GET.get('horizon', 5))
    tk = normalize_ticker(ticker)
    
    # --- 2. データ取得 ---
    print(f"Debug: Fetching OHLC for {tk}...") # ★fetch前
    df = fetch_ohlc(tk, interval=frame)
    name = get_name_safe(tk)

    # ★ dfの状態確認
    if df is None:
        print("Error: df is None")
    elif df.empty:
        print("Error: df is empty")
    else:
        print(f"Debug: df shape = {df.shape}")
        print(f"Debug: df tail(1) = \n{df.tail(1)}")

    if df is None or df.empty:
        print("=== Debug: Returned 404 (No data) ===") # ★終了箇所特定
        return JsonResponse({
            "ticker": ticker, "name": name, "asof": None, "close": None,
            "expected_value": None, "probability": None, "model": "No data available"
        }, status=404)

    # --- 3. 特徴量生成 ---
    # 外部データの取得確認（念のため）
    print("Debug: Downloading ^N225 for check...")
    n225 = yf.download("^N225", start="2018-01-01", end=pd.Timestamp.today().strftime('%Y-%m-%d'), progress=False)
    print(f"Debug: ^N225 empty? = {n225.empty}")

    print("Debug: Calculating indicators...") # ★計算開始
    feats = calculate_indicators(df, frame=frame)
    
    # ★ featsの状態確認 (ここで0行になっていないか？)
    if feats.empty:
        print("Error: feats is empty (All rows dropped?)")
    else:
        print(f"Debug: feats shape = {feats.shape}")
        print(f"Debug: feats tail(1) indices = {feats.index[-1]}")

    if feats.empty:
        print("=== Debug: Returned 500 (Feature calc failed) ===") # ★終了箇所特定
        return JsonResponse({
            "ticker": ticker, "name": name, "asof": None, "close": None,
            "expected_value": None, "probability": None, "model": "Feature calculation failed"
        }, status=500)
    
    # --- 4. 予測のためのデータ準備 ---
    last_row = feats.iloc[[-1]].copy()
    # fill_value=0.0 で埋めているので、ここでNaNになることはないはず
    X = last_row.reindex(columns=FEATURE_COLS, fill_value=0.0)
    
    print(f"Debug: X shape for prediction = {X.shape}") # ★予測データ確認

    # --- 5. モデル読込と予測 ---
    model = get_model()
    
    try:
        proba = float(model.predict_proba(X)[0][1])
        print(f"Debug: Prediction successful. Calculated proba = {proba}")
    except Exception as e:
        print(f"[WARN] 予測時エラー: {e}")
        import traceback
        traceback.print_exc() # ★詳細なエラー内容を表示
        return JsonResponse({"error": str(e)}, status=500)
    
    # --- 6. 値の確定 ---
    close = float(feats["Close"].iloc[-1].item())
    asof = str(feats.index[-1].date())
    expected_value = round(close * (1 + (proba - 0.5)), 2)

    print("=== Debug: Successfully returned JSON ===") # ★正常終了
    
    return JsonResponse({
        "ticker": ticker,
        "name": name,
        "asof": asof,
        "close": close,
        "expected_value": expected_value,
        "probability": round(proba, 4),
        "model": type(model).__name__
    })

    # --- 特徴量生成（学習時と同じ関数を利用） ---
    n225 = yf.download("^N225", start="2018-01-01", end=pd.Timestamp.today().strftime('%Y-%m-%d'))
    n225_close = n225["Close"] if not n225.empty else None
    feats = calculate_indicators(df, frame=frame)

    
    # --- 最新行を取得 ---
    last_row = feats.iloc[[-1]].copy()
    
    # --- 必要な列のみ reindex（足りない列は0埋め） ---
    X = last_row.reindex(columns=FEATURE_COLS, fill_value=0.0)
    
    # --- モデル読込 ---
    model = get_model()

    model = get_model()
    print("[DEBUG] model.feature_names_in_:", model.feature_names_in_)

    
    # --- 予測 ---
    try:
        proba = float(model.predict_proba(X)[0][1])
    except Exception as e:
        print(f"[WARN] 予測時エラー: {e}")
        return JsonResponse({"error": str(e)}, status=500)
    
    close = float(feats["Close"].iloc[-1].item())

    asof = str(feats.index[-1].date())
    name = get_name_safe(tk)
    
    return JsonResponse({
        "ticker": ticker,
        "name": name,
        "asof": asof,
        "close": close,
        "probability": round(proba, 4)
    })


