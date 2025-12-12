# -*- coding: utf-8 -*-
"""
改良版: リターン統計を保存
予測時に実際の分布を使って期待値を計算
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

sys.path.append(str(Path(__file__).parent))
from indicators import calculate_indicators, FEATURE_COLS

TICKERS = ["7203.T", "6501.T", "9984.T", "8035.T"]
START_DATE = "2018-01-01"
END_DATE = "2025-01-01"
SEED = 42
TARGET_THRESHOLD = 0.005
COST_RATE = 0.001

def sharpe(ret, periods_per_year=252):
    ret = ret.dropna()
    if len(ret) < 2:
        return 0.0
    mu = ret.mean() * periods_per_year
    sig = ret.std(ddof=1) * np.sqrt(periods_per_year)
    return float(mu / sig) if sig != 0 else 0.0

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
    all_data = []
    
    for ticker in tickers:
        print(f"Processing {ticker}...")
        df = yf.download(ticker, start=START_DATE, end=END_DATE, 
                        interval="1d", auto_adjust=True, progress=False)
        
        if df.empty:
            print(f"  Warning: {ticker} - No data")
            continue
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = calculate_indicators(df, frame='1d', ticker=ticker)
        
        if not df.empty:
            all_data.append(df)
            print(f"  ✓ {len(df)} rows")
    
    if not all_data:
        raise ValueError("No data available")
    
    full = pd.concat(all_data, axis=0)
    
    full = full.groupby('Ticker').apply(lambda x: x.assign(
        Daily_Return=x['Close'].pct_change().shift(-1),
        Target=(x['Close'].pct_change().shift(-1) > TARGET_THRESHOLD).astype(int)
    )).reset_index(drop=True)
    
    return full

def define_feature_sets():
    base = [
        'Close', 'High', 'Low', 'Open', 'Volume',
        'RSI', 'MACD', 'MACD_Signal', 'ROC_10',
        'Pct_Change_1D', 'Pct_Change_3D',
        'Vol_Ratio', 'Volatility_10',
    ]
    
    all_feats = [f for f in FEATURE_COLS if f not in ['Ticker', 'Raw_Close', 'Return_5D']]
    
    return {
        'Base': base,
        'All': all_feats
    }

# ★ 新機能: リターン統計の計算
def calculate_return_statistics(df, proba_all, threshold):
    """
    確率区間ごとのリターン統計を計算
    """
    stats_df = pd.DataFrame({
        'proba': proba_all,
        'return': df['Daily_Return']
    }).dropna()
    
    # 確率を10分位に分割
    stats_df['decile'] = pd.qcut(stats_df['proba'], q=10, labels=False, duplicates='drop')
    
    # 各区間の統計
    return_stats = stats_df.groupby('decile')['return'].agg([
        ('mean', 'mean'),
        ('std', 'std'),
        ('median', 'median'),
        ('q25', lambda x: x.quantile(0.25)),
        ('q75', lambda x: x.quantile(0.75))
    ]).to_dict('index')
    
    # 全体統計
    overall_stats = {
        'win_mean': stats_df[stats_df['return'] > 0]['return'].mean(),
        'loss_mean': stats_df[stats_df['return'] <= 0]['return'].mean(),
        'overall_std': stats_df['return'].std()
    }
    
    return {
        'decile_stats': return_stats,
        'overall': overall_stats,
        'threshold': threshold
    }

def main():
    print("=" * 60)
    print("Daily Hybrid Model Training (with Return Stats)")
    print("=" * 60)
    
    df = fetch_and_prepare_data(TICKERS)
    print(f"\nTotal data points: {len(df)}")
    print(f"Target distribution: {df['Target'].mean():.2%} positive")
    
    feature_sets = define_feature_sets()
    
    required_cols = set(feature_sets['Base']) | set(feature_sets['All']) | {'Target', 'Daily_Return', 'Ticker'}
    available_cols = set(df.columns)
    missing = required_cols - available_cols
    
    if missing:
        print(f"\nWarning: Missing columns: {missing}")
        feature_sets['Base'] = [c for c in feature_sets['Base'] if c in available_cols]
        feature_sets['All'] = [c for c in feature_sets['All'] if c in available_cols]
    
    df = df.dropna(subset=['Target', 'Daily_Return'])
    df = df.sort_index()
    
    n = len(df)
    i1, i2 = int(n * 0.6), int(n * 0.8)
    
    idx_tr = df.index[:i1]
    idx_va = df.index[i1:i2]
    idx_te = df.index[i2:]
    
    X_tr_xgb = df.loc[idx_tr, feature_sets['Base']]
    X_va_xgb = df.loc[idx_va, feature_sets['Base']]
    X_te_xgb = df.loc[idx_te, feature_sets['Base']]
    
    lgb_cols = feature_sets['All'] + ['Ticker']
    X_tr_lgb = df.loc[idx_tr, lgb_cols].copy()
    X_va_lgb = df.loc[idx_va, lgb_cols].copy()
    X_te_lgb = df.loc[idx_te, lgb_cols].copy()
    
    for X in [X_tr_lgb, X_va_lgb, X_te_lgb]:
        X['Ticker'] = X['Ticker'].astype('category')
    
    y_tr = df.loc[idx_tr, 'Target']
    y_va = df.loc[idx_va, 'Target']
    y_te = df.loc[idx_te, 'Target']
    
    ret_va = df.loc[idx_va, 'Daily_Return']
    ret_te = df.loc[idx_te, 'Daily_Return']
    
    print(f"\nTrain: {len(idx_tr)}, Valid: {len(idx_va)}, Test: {len(idx_te)}")
    
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
    
    print("\n[1/2] Training LightGBM...")
    lgbm.fit(
        X_tr_lgb, y_tr,
        eval_set=[(X_va_lgb, y_va)],
        eval_metric="auc",
        categorical_feature=['Ticker'],
        callbacks=[early_stopping(200), log_evaluation(0)]
    )
    
    print("\n[2/2] Training XGBoost...")
    xgb.fit(
        X_tr_xgb, y_tr,
        eval_set=[(X_va_xgb, y_va)],
        verbose=False
    )
    
    proba_va_lgb = lgbm.predict_proba(X_va_lgb)[:, 1]
    proba_te_lgb = lgbm.predict_proba(X_te_lgb)[:, 1]
    
    proba_va_xgb = xgb.predict_proba(X_va_xgb)[:, 1]
    proba_te_xgb = xgb.predict_proba(X_te_xgb)[:, 1]
    
    w_xgb, w_lgb = 0.6, 0.4
    proba_va_ens = w_xgb * proba_va_xgb + w_lgb * proba_va_lgb
    proba_te_ens = w_xgb * proba_te_xgb + w_lgb * proba_te_lgb
    
    thr = tune_threshold(proba_va_ens, idx_va, ret_va)
    print(f"\nOptimal Threshold: {thr:.3f}")
    
    # ★ リターン統計の計算
    print("\n" + "=" * 60)
    print("Calculating Return Statistics...")
    print("=" * 60)
    
    X_all_lgb = df[lgb_cols].copy()
    X_all_lgb['Ticker'] = X_all_lgb['Ticker'].astype('category')
    X_all_xgb = df[feature_sets['Base']]
    
    proba_all_lgb = lgbm.predict_proba(X_all_lgb)[:, 1]
    proba_all_xgb = xgb.predict_proba(X_all_xgb)[:, 1]
    proba_all_ens = w_xgb * proba_all_xgb + w_lgb * proba_all_lgb
    
    return_stats = calculate_return_statistics(df, proba_all_ens, thr)
    
    print("\nReturn Statistics by Probability Decile:")
    for decile, stats in return_stats['decile_stats'].items():
        print(f"  Decile {decile}: mean={stats['mean']:.2%}, std={stats['std']:.2%}")
    
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
    eval_model("Ensemble", proba_te_ens)
    
    print("\n" + "=" * 60)
    print("Retraining on full dataset...")
    print("=" * 60)
    
    y_full = df['Target']
    
    lgbm.fit(X_all_lgb, y_full, categorical_feature=['Ticker'])
    xgb.fit(X_all_xgb, y_full)
    
    joblib.dump(lgbm, "lgbm_final.pkl")
    joblib.dump(xgb, "xgb_final.pkl")
    joblib.dump({
        'threshold': thr,
        'w_xgb': w_xgb,
        'w_lgb': w_lgb,
        'base_features': feature_sets['Base'],
        'all_features': feature_sets['All'],
        'return_stats': return_stats  # ★ 追加
    }, "model_config.pkl")
    
    print("\n✓ Models saved with return statistics")

if __name__ == "__main__":
    main()
