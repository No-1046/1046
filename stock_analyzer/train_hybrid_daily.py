# -*- coding: utf-8 -*-
"""
日足データ × 複数銘柄対応
ハイブリッドモデル: XGBoost(Base) + LightGBM(All)
indicators.py の特徴量を使用して学習
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import yfinance as yf
import joblib

from lightgbm import LGBMClassifier, early_stopping, log_evaluation
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from pathlib import Path

# indicators.py をインポート
sys.path.append(str(Path(__file__).parent))
from indicators import calculate_indicators, FEATURE_COLS

# ============== 設定 ==============
TICKERS = ["7203.T", "6501.T", "9984.T", "8035.T"]  # トヨタ, 日立, ソフトバンク, 東京エレクトロン
START_DATE = "2018-01-01"
END_DATE = "2025-01-01"
SEED = 42
TARGET_THRESHOLD = 0.005  # 翌日リターン +0.5%以上で Target=1
COST_RATE = 0.001
# ==================================

def sharpe(ret, periods_per_year=252):
    ret = ret.dropna()
    if len(ret) < 2:
        return 0.0
    mu = ret.mean() * periods_per_year
    sig = ret.std(ddof=1) * np.sqrt(periods_per_year)
    if sig == 0:
        return 0.0
    return float(mu / sig)

def max_drawdown(cum):
    if len(cum) == 0:
        return 0.0
    peak = cum.cummax()
    dd = cum / peak - 1.0
    return float(dd.min())

def backtest(index, ret_next, signal, costs=COST_RATE):
    bt = pd.DataFrame(index=index)
    bt["ret_next"] = ret_next
    bt["signal"] = signal.astype(int)
    bt = bt.dropna(subset=["ret_next"]).copy()

    bt["strategy_ret"] = bt["signal"] * bt["ret_next"]
    bt["trade"] = (bt["signal"] == 1) & (bt["signal"].shift(1).fillna(0).astype(int) == 0)
    bt.loc[bt["trade"], "strategy_ret"] = bt.loc[bt["trade"], "strategy_ret"] - costs

    bt["cum_market"] = (1 + bt["ret_next"]).cumprod()
    bt["cum_strategy"] = (1 + bt["strategy_ret"]).cumprod()

    mkt_ret = float(bt["cum_market"].iloc[-1] - 1) if len(bt) > 0 else 0.0
    strat_ret = float(bt["cum_strategy"].iloc[-1] - 1) if len(bt) > 0 else 0.0
    win_rate = float((bt.loc[bt["signal"] == 1, "strategy_ret"] > 0).mean()) if (bt["signal"] == 1).sum() > 0 else 0.0

    sr_mkt = sharpe(bt["ret_next"])
    sr_str = sharpe(bt["strategy_ret"])
    mdd_mkt = max_drawdown(bt["cum_market"])
    mdd_str = max_drawdown(bt["cum_strategy"])

    return {
        "Market Return": round(mkt_ret * 100, 2),
        "Strategy Return": round(strat_ret * 100, 2),
        "WinRate": round(win_rate * 100, 2),
        "Sharpe(Mkt)": round(sr_mkt, 2),
        "Sharpe(Str)": round(sr_str, 2),
        "MaxDD(Mkt)": round(mdd_mkt * 100, 2),
        "MaxDD(Str)": round(mdd_str * 100, 2),
    }

def tune_threshold(proba_valid, valid_index, ret_next_valid, costs=COST_RATE):
    dfv = pd.DataFrame({
        "proba": pd.Series(proba_valid, index=valid_index),
        "ret": pd.Series(ret_next_valid)
    }).dropna()

    best_thr, best_sharpe = 0.5, -1e18

    for thr in np.linspace(0.5, 0.85, 71):
        sig = (dfv["proba"] >= thr).astype(int)
        trades = (sig == 1) & (sig.shift(1).fillna(0).astype(int) == 0)
        strat_ret = sig * dfv["ret"]
        strat_ret.loc[trades] = strat_ret.loc[trades] - costs

        sr = sharpe(strat_ret)
        if sr > best_sharpe:
            best_sharpe = sr
            best_thr = float(thr)

    return best_thr

def fetch_and_prepare_data(tickers):
    """複数銘柄のデータを取得して結合"""
    all_data = []
    
    for ticker in tickers:
        print(f"Processing {ticker}...")
        df = yf.download(ticker, start=START_DATE, end=END_DATE, 
                        interval="1d", auto_adjust=True, progress=False)
        
        if df.empty:
            print(f"  Warning: {ticker} - No data")
            continue
            
        # MultiIndex解消
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 特徴量計算
        df = calculate_indicators(df, frame='1d', ticker=ticker)
        
        if not df.empty:
            all_data.append(df)
            print(f"  ✓ {len(df)} rows")
    
    if not all_data:
        raise ValueError("No data available")
    
    # 結合
    full = pd.concat(all_data, axis=0)
    
    # ターゲット作成
    full = full.groupby('Ticker').apply(lambda x: x.assign(
        Daily_Return=x['Close'].pct_change().shift(-1),
        Target=(x['Close'].pct_change().shift(-1) > TARGET_THRESHOLD).astype(int)
    )).reset_index(drop=True)
    
    return full

def define_feature_sets():
    """特徴量セットの定義"""
    # Base特徴量（コア指標のみ）
    base = [
        'Close', 'High', 'Low', 'Open', 'Volume',
        'RSI', 'MACD', 'MACD_Signal', 'ROC_10',
        'Pct_Change_1D', 'Pct_Change_3D',
        'Vol_Ratio', 'Volatility_10',
    ]
    
    # All特徴量（FEATURE_COLSからTickerとRaw_Closeを除外）
    all_feats = [f for f in FEATURE_COLS if f not in ['Ticker', 'Raw_Close', 'Return_5D']]
    
    return {
        'Base': base,
        'All': all_feats
    }

def main():
    print("=" * 60)
    print("Daily Hybrid Model Training")
    print("=" * 60)
    
    # データ準備
    df = fetch_and_prepare_data(TICKERS)
    print(f"\nTotal data points: {len(df)}")
    print(f"Target distribution: {df['Target'].mean():.2%} positive")
    
    # 特徴量セット
    feature_sets = define_feature_sets()
    
    # 使用する列を確定
    required_cols = set(feature_sets['Base']) | set(feature_sets['All']) | {'Target', 'Daily_Return', 'Ticker'}
    available_cols = set(df.columns)
    missing = required_cols - available_cols
    
    if missing:
        print(f"\nWarning: Missing columns: {missing}")
        # 欠損列を除外
        feature_sets['Base'] = [c for c in feature_sets['Base'] if c in available_cols]
        feature_sets['All'] = [c for c in feature_sets['All'] if c in available_cols]
    
    # データ分割準備
    df = df.dropna(subset=['Target', 'Daily_Return'])
    df = df.sort_index()
    
    n = len(df)
    i1, i2 = int(n * 0.6), int(n * 0.8)
    
    idx_tr = df.index[:i1]
    idx_va = df.index[i1:i2]
    idx_te = df.index[i2:]
    
    # XGBoost用（Base特徴量）
    X_tr_xgb = df.loc[idx_tr, feature_sets['Base']]
    X_va_xgb = df.loc[idx_va, feature_sets['Base']]
    X_te_xgb = df.loc[idx_te, feature_sets['Base']]
    
    # LightGBM用（All特徴量 + Ticker）
    lgb_cols = feature_sets['All'] + ['Ticker']
    X_tr_lgb = df.loc[idx_tr, lgb_cols].copy()
    X_va_lgb = df.loc[idx_va, lgb_cols].copy()
    X_te_lgb = df.loc[idx_te, lgb_cols].copy()
    
    # Tickerをカテゴリ化
    for X in [X_tr_lgb, X_va_lgb, X_te_lgb]:
        X['Ticker'] = X['Ticker'].astype('category')
    
    y_tr = df.loc[idx_tr, 'Target']
    y_va = df.loc[idx_va, 'Target']
    y_te = df.loc[idx_te, 'Target']
    
    ret_va = df.loc[idx_va, 'Daily_Return']
    ret_te = df.loc[idx_te, 'Daily_Return']
    
    print(f"\nTrain: {len(idx_tr)}, Valid: {len(idx_va)}, Test: {len(idx_te)}")
    
    # モデル定義
    print("\n" + "=" * 60)
    print("Training Models...")
    print("=" * 60)
    
    lgbm = LGBMClassifier(
        objective="binary",
        learning_rate=0.03,
        num_leaves=63,
        subsample=0.8,
        colsample_bytree=0.8,
        n_estimators=2000,
        reg_alpha=1e-6,
        reg_lambda=1e-6,
        random_state=SEED
    )
    
    xgb = XGBClassifier(
        objective="binary:logistic",
        learning_rate=0.03,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        n_estimators=2000,
        reg_alpha=0.0,
        reg_lambda=1.0,
        random_state=SEED,
        eval_metric="logloss"
    )
    
    # 学習
    print("\n[1/2] Training LightGBM (All features)...")
    lgbm.fit(
        X_tr_lgb, y_tr,
        eval_set=[(X_va_lgb, y_va)],
        eval_metric="auc",
        categorical_feature=['Ticker'],
        callbacks=[early_stopping(200), log_evaluation(0)]
    )
    
    print("\n[2/2] Training XGBoost (Base features)...")
    xgb.fit(
        X_tr_xgb, y_tr,
        eval_set=[(X_va_xgb, y_va)],
        verbose=False
    )
    
    # 予測
    proba_va_lgb = lgbm.predict_proba(X_va_lgb)[:, 1]
    proba_te_lgb = lgbm.predict_proba(X_te_lgb)[:, 1]
    
    proba_va_xgb = xgb.predict_proba(X_va_xgb)[:, 1]
    proba_te_xgb = xgb.predict_proba(X_te_xgb)[:, 1]
    
    # アンサンブル
    w_xgb, w_lgb = 0.6, 0.4
    proba_va_ens = w_xgb * proba_va_xgb + w_lgb * proba_va_lgb
    proba_te_ens = w_xgb * proba_te_xgb + w_lgb * proba_te_lgb
    
    # しきい値最適化
    thr = tune_threshold(proba_va_ens, idx_va, ret_va)
    print(f"\nOptimal Threshold: {thr:.3f}")
    
    # 評価
    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    
    def eval_model(name, proba_te):
        pred_te = (proba_te >= thr).astype(int)
        acc = accuracy_score(y_te, pred_te)
        f1 = f1_score(y_te, pred_te)
        auc = roc_auc_score(y_te, proba_te)
        bt = backtest(idx_te, ret_te, pred_te)
        
        print(f"\n{name}")
        print(f"  Accuracy: {acc:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        print(f"  ROC-AUC:  {auc:.4f}")
        print(f"  Backtest: Strat Return={bt['Strategy Return']}%, "
              f"Sharpe={bt['Sharpe(Str)']}, WinRate={bt['WinRate']}%")
    
    eval_model("LightGBM (All)", proba_te_lgb)
    eval_model("XGBoost (Base)", proba_te_xgb)
    eval_model("Ensemble (0.6*XGB + 0.4*LGBM)", proba_te_ens)
    
    # 全データで再学習
    print("\n" + "=" * 60)
    print("Retraining on full dataset...")
    print("=" * 60)
    
    X_full_lgb = df[lgb_cols].copy()
    X_full_lgb['Ticker'] = X_full_lgb['Ticker'].astype('category')
    X_full_xgb = df[feature_sets['Base']]
    y_full = df['Target']
    
    lgbm.fit(X_full_lgb, y_full, categorical_feature=['Ticker'])
    xgb.fit(X_full_xgb, y_full)
    
    # モデル保存
    joblib.dump(lgbm, "lgbm_final.pkl")
    joblib.dump(xgb, "xgb_final.pkl")
    joblib.dump({
        'threshold': thr,
        'w_xgb': w_xgb,
        'w_lgb': w_lgb,
        'base_features': feature_sets['Base'],
        'all_features': feature_sets['All']
    }, "model_config.pkl")
    
    print("\n✓ Models saved:")
    print("  - lgbm_final.pkl")
    print("  - xgb_final.pkl")
    print("  - model_config.pkl")

if __name__ == "__main__":
    main()