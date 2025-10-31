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
MODEL_PATH = settings.BASE_DIR / "model.pkl"

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
    period = f"{years}y" if interval in ("1d", "1wk") else f"{max(years, 10)}y"
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
    if _model is not None: return _model
    if MODEL_PATH.exists():
        _model = joblib.load(MODEL_PATH)
        return _model
    class Baseline:
        feature_names_in_ = FEATURE_COLS
        def predict_proba(self, X: pd.DataFrame):
            z = 0.012*(X["rsi14"]-50) + 6.0*X["ma5_20"] + 3.0*X["ma_slope20"] \
                + 1.0*(X["brk20"]-1.0) - 1.0*np.clip(-X["dd_252"],0,None)
            p = 1/(1+np.exp(-z))
            p = np.clip(p, 0.01, 0.99)
            return np.c_[1-p, p]
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
    ticker = request.GET.get('ticker', '6501')
    frame = request.GET.get('frame', '1d')
    horizon = int(request.GET.get('horizon', 5))
    tk = normalize_ticker(ticker)
    
    # --- データ取得 ---
    df = fetch_ohlc(tk, interval=frame)
    if df is None or df.empty:
        return JsonResponse({"error": f"{ticker}: no data found"}, status=404)
    
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
    
    # --- 予測 ---
    try:
        proba = float(model.predict_proba(X)[0][1])
    except Exception as e:
        print(f"[WARN] 予測時エラー: {e}")
        return JsonResponse({"error": str(e)}, status=500)
    
    close = float(feats["Close"].iloc[-1])
    asof = str(feats.index[-1].date())
    name = get_name_safe(tk)
    
    return JsonResponse({
        "ticker": ticker,
        "name": name,
        "asof": asof,
        "close": close,
        "probability": round(proba, 4)
    })
