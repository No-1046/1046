import re
import numpy as np
import pandas as pd
import yfinance as yf
import joblib
import json
from datetime import datetime

from django.http import JsonResponse, HttpRequest
from django.shortcuts import render
from django.conf import settings
from django.core.cache import cache
from .indicators import calculate_indicators

# モデルパス
MODEL_DIR = settings.BASE_DIR / "stock_analyzer"
LGBM_PATH = MODEL_DIR / "lgbm_final.pkl"
XGB_PATH = MODEL_DIR / "xgb_final.pkl"
CONFIG_PATH = MODEL_DIR / "model_config.pkl"

def tz_naive_index(df): 
    return df.tz_localize(None) if df.index.tz is not None else df

def normalize_ticker(s: str) -> str:
    s = s.strip().upper()
    if re.fullmatch(r"\d{4}", s):
        return f"{s}.T"
    return s

def fetch_ohlc(ticker: str, interval: str = "1d", years: int = 5) -> pd.DataFrame:
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
def get_models():
    """ハイブリッドモデルとコンフィグをロード"""
    global _models
    if _models:
        return _models
    
    try:
        if LGBM_PATH.exists() and XGB_PATH.exists() and CONFIG_PATH.exists():
            _models = {
                'lgbm': joblib.load(LGBM_PATH),
                'xgb': joblib.load(XGB_PATH),
                'config': joblib.load(CONFIG_PATH)
            }
            print(f"✓ Loaded hybrid models (threshold={_models['config']['threshold']:.3f})")
        else:
            print("⚠ Model files not found - using fallback")
            _models = None
    except Exception as e:
        print(f"⚠ Error loading models: {e}")
        _models = None
    
    return _models

def index(request: HttpRequest):
    return render(request, 'stock_analyzer/index.html')

def some_feature_view(request):
    profile = getattr(request.user, "userprofile", None)
    if profile is not None:
        profile.usage_count += 1
        profile.save()

def get_series(request):
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

    return JsonResponse({
        "ticker": tk,
        "name": name,
        "frame": frame,
        "rows": rows[-1200:]
    }, safe=False)

def get_predict(request: HttpRequest):
    """ハイブリッドモデルで予測"""
    ticker = request.GET.get('ticker', '6501')
    frame = request.GET.get('frame', '1d')
    tk = normalize_ticker(ticker)
    
    # 検索履歴を保存
    save_search_history(request, tk)
    
    # データ取得
    df = fetch_ohlc(tk, interval=frame)
    name = get_name_safe(tk)

    if df is None or df.empty:
        return JsonResponse({
            "ticker": ticker, "name": name, "asof": None, "last_close": None,
            "pred_close": None, "prob_up": None, "model": "No data available"
        }, status=404)

    # 特徴量生成
    try:
        feats = calculate_indicators(df, frame=frame, ticker=tk)
    except Exception as e:
        print(f"Error in calculate_indicators: {e}")
        return JsonResponse({
            "ticker": ticker, "name": name, "asof": None, "last_close": None,
            "pred_close": None, "prob_up": None, "model": "Feature calculation failed"
        }, status=500)
    
    if feats.empty:
        return JsonResponse({
            "ticker": ticker, "name": name, "asof": None, "last_close": None,
            "pred_close": None, "prob_up": None, "model": "No valid features"
        }, status=500)
    
    # モデルロード
    models = get_models()
    
    if models is None:
        # Fallback: 単純な0.5予測
        close = float(feats["Close"].iloc[-1])
        asof = str(feats.index[-1].date())
        return JsonResponse({
            "ticker": ticker,
            "name": name,
            "asof": asof,
            "last_close": close,
            "pred_close": close,
            "prob_up": 0.5,
            "model": "Fallback (no trained model)"
        })
    
    # 予測データ準備
    last_row = feats.iloc[[-1]].copy()
    
    config = models['config']
    base_cols = config['base_features']
    all_cols = config['all_features']
    
    # XGBoost用（Base特徴量）
    X_xgb = last_row.reindex(columns=base_cols, fill_value=0.0)
    
    # LightGBM用（All特徴量 + Ticker）
    X_lgb = last_row.reindex(columns=all_cols + ['Ticker'], fill_value=0.0)
    if 'Ticker' in X_lgb.columns:
        X_lgb['Ticker'] = X_lgb['Ticker'].astype('category')
    
    try:
        # 予測
        proba_xgb = float(models['xgb'].predict_proba(X_xgb)[0][1])
        proba_lgb = float(models['lgbm'].predict_proba(X_lgb)[0][1])
        
        # アンサンブル
        w_xgb = config.get('w_xgb', 0.6)
        w_lgb = config.get('w_lgb', 0.4)
        proba = w_xgb * proba_xgb + w_lgb * proba_lgb
        
        print(f"Prediction: XGB={proba_xgb:.4f}, LGBM={proba_lgb:.4f}, Ensemble={proba:.4f}")
        
    except Exception as e:
        print(f"Prediction error: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
    
    # 結果計算
    close = float(feats["Close"].iloc[-1])
    asof = str(feats.index[-1].date())
    
    # ★ リターン統計を使った期待値計算
    config = models['config']
    return_stats = config.get('return_stats')
    
    if return_stats:
        # 確率から分位を推定
        proba_capped = max(0.0, min(1.0, proba))
        decile = int(proba_capped * 9.999)  # 0-9のインデックス
        
        decile_stats = return_stats['decile_stats'].get(decile)
        if decile_stats:
            # その分位の平均リターンを使用
            expected_return = decile_stats['mean']
            
            # 時間軸でスケール調整（日足基準なので）
            time_scale = {'1d': 1.0, '1wk': 5.0, '1mo': 21.0}.get(frame, 1.0)
            expected_return *= time_scale
            
            pred_close = round(close * (1 + expected_return), 2)
            
            print(f"Frame={frame}, Proba={proba:.4f}, Decile={decile}, "
                  f"Expected Return={expected_return:.4%}, Pred={pred_close}")
        else:
            # fallback
            expected_return = (proba - 0.5) * 0.06
            pred_close = round(close * (1 + expected_return), 2)
    else:
        # リターン統計がない場合（旧モデル）
        deviation = proba - 0.5
        scale_map = {'1d': 0.03, '1wk': 0.08, '1mo': 0.15}
        scale = scale_map.get(frame, 0.03)
        amplified = np.tanh(deviation * 3)
        expected_return = amplified * scale
        pred_close = round(close * (1 + expected_return), 2)
        
        print(f"Frame={frame}, Proba={proba:.4f}, Change={expected_return:.4%} (no stats)")
    
    return JsonResponse({
        "ticker": ticker,
        "name": name,
        "asof": asof,
        "last_close": close,
        "pred_close": pred_close,
        "prob_up": round(proba, 4),
        "model": f"Hybrid (XGB={w_xgb}, LGBM={w_lgb})"
    })

# ============== 新機能: スキャン & 検索履歴 ==============

def save_search_history(request, ticker):
    """検索履歴を保存（セッション or DB）"""
    # セッションに保存
    history = request.session.get('search_history', [])
    
    # 既存エントリを削除
    history = [h for h in history if h['ticker'] != ticker]
    
    # 新しいエントリを先頭に追加
    history.insert(0, {
        'ticker': ticker,
        'timestamp': datetime.now().isoformat()
    })
    
    # 最大20件まで保持
    request.session['search_history'] = history[:20]

def get_search_history(request):
    """検索履歴を取得"""
    history = request.session.get('search_history', [])
    return JsonResponse({'history': history})

def get_top_stocks(request):
    """スキャン結果から上位銘柄を取得"""
    # キャッシュをチェック（5分間有効）
    cached = cache.get('top_stocks')
    if cached:
        return JsonResponse(cached)
    
    # 保存された結果を読み込み
    results_path = MODEL_DIR / "scan_results.json"
    
    if not results_path.exists():
        return JsonResponse({
            'error': 'No scan results available',
            'message': 'スキャンを実行してください'
        }, status=404)
    
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # キャッシュに保存
        cache.set('top_stocks', data, 300)  # 5分
        
        return JsonResponse(data)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def trigger_scan(request):
    """スキャンを手動でトリガー（管理者のみ）"""
    # 本番では権限チェックが必要
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # バックグラウンドタスクとして実行（Celeryなど）
    # ここでは簡易的に同期実行
    try:
        from . import scanner
        results = scanner.scan_all_stocks(max_stocks=20)  # テスト用に20銘柄
        scanner.save_results(results)
        
        return JsonResponse({
            'status': 'completed',
            'count': len(results),
            'top_10': results[:10]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)