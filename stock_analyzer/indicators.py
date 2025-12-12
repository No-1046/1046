# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import yfinance as yf

# ========== Utility ==========
def tz_naive_index(df):
    return df.tz_localize(None) if df.index.tz is not None else df

# ========== Feature Engineering Core ==========
def calculate_indicators(df: pd.DataFrame, frame: str = "1d", ticker: str = None) -> pd.DataFrame:
    """
    学習時と同じ特徴量を生成する（ラグ特徴量含む）
    """
    df = df.copy()
    
    # indexが日付型でない場合は変換
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df = tz_naive_index(df)
    df = df.sort_index()

    # --- Basic ----
    if "Close" not in df.columns and "c" in df.columns:
         df.rename(columns={"c": "Close", "o": "Open", "h": "High", "l": "Low", "v": "Volume"}, inplace=True)

    df["Raw_Close"] = df["Close"]
    df["Pct_Change_1D"] = df["Close"].pct_change()
    df["Pct_Change_3D"] = df["Close"].pct_change(3)

    # Volume missing check
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    df["Volume_Change"] = df["Volume"].pct_change(5) * 100  # 学習時と同じ5日

    # RSI (14)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=14 - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=14 - 1, adjust=False).mean()
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    df["RSI"] = 100 - (100 / (1 + rs))

    # ROC10
    df["ROC_10"] = df["Close"].pct_change(10) * 100

    # MACD
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # KDJ (Stochastics)
    low9 = df["Low"].rolling(9).min()
    high9 = df["High"].rolling(9).max()
    denom = (high9 - low9).replace(0, 1e-9)
    percent_k = ((df["Close"] - low9) / denom) * 100
    df["KDJ_D"] = percent_k.rolling(3).mean()
    df["KDJ_J"] = df["KDJ_D"].rolling(3).mean()

    # Volatility
    df["Volatility_10"] = df["Close"].pct_change().rolling(10).std() * 100
    vol_mean = df["Volatility_10"].rolling(20).mean().replace(0, 1e-9)
    df["Volatility_Ratio"] = df["Volatility_10"] / vol_mean

    # Volume indicators
    vol_ma = df["Volume"].rolling(20).mean().replace(0, 1e-9)
    df["Vol_Ratio"] = df["Volume"] / vol_ma
    df["Volume_Surge"] = (df["Vol_Ratio"] > 2.0).astype(int)

    # Return horizon
    df["Return_5D"] = df["Close"].pct_change(5)

    # RSI change
    df["RSI_Change"] = df["RSI"].diff()

    # AD Line
    hl_range = (df["High"] - df["Low"]).replace(0, 1e-9)
    mfm = (((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / hl_range)
    mfv = mfm * df["Volume"]
    df["AD_Line"] = mfv.cumsum()
    df["AD_Line_ROC"] = df["AD_Line"].pct_change() * 100

    # --- Market Indicators (N225) ---
    try:
        n225 = yf.download("^N225", period="2y", interval=frame, auto_adjust=True, progress=False)
        if n225 is None or n225.empty:
            raise ValueError("Empty N225 data")
            
        n225 = tz_naive_index(n225)
        n225_aligned = n225["Close"].reindex(df.index).fillna(method='ffill').fillna(0)
        
        df["IDX_N225"] = n225_aligned
        df["Market_Trend_1D"] = n225_aligned.pct_change(1).shift(1).fillna(0) * 100
        df["Market_Trend_5D"] = n225_aligned.pct_change(5).shift(1).fillna(0) * 100
        df["Corr_N225_30"] = df["Close"].rolling(30).corr(n225_aligned).shift(1).fillna(0)
    except Exception:
        df["IDX_N225"] = 0.0
        df["Market_Trend_1D"] = 0.0
        df["Market_Trend_5D"] = 0.0
        df["Corr_N225_30"] = 0.0

    # --- Market Indicators (TNX) - 学習時には使われていないが念のため ---
    try:
        tnx = yf.download("^TNX", period="2y", interval=frame, auto_adjust=True, progress=False)
        if tnx is None or tnx.empty:
            raise ValueError("Empty TNX data")

        tnx = tz_naive_index(tnx)
        tnx_aligned = tnx["Close"].reindex(df.index).fillna(method='ffill').fillna(0)
        
        df["TNX_Change_1D"] = tnx_aligned.pct_change().fillna(0)
        df["TNX_Change_5D"] = tnx_aligned.pct_change(5).fillna(0)
    except Exception:
        df["TNX_Change_1D"] = 0.0
        df["TNX_Change_5D"] = 0.0

    # Cross features
    df["RSI_x_MACD_Hist"] = (df["RSI"] * df["MACD_Hist"]).fillna(0)
    df["Vol_Ratio_x_Market_Trend_5D"] = (df["Vol_Ratio"] * df["Market_Trend_5D"]).fillna(0)
    
    # ★★★ ラグ特徴量の追加（学習時と同じ）★★★
    LAG_DAYS = 5
    lag_cols = [
        'RSI', 'MACD', 'MACD_Signal', 'Volume', 'Close', 'ROC_10', 'Vol_Ratio',
        'Pct_Change_1D', 'Pct_Change_3D', 'AD_Line_ROC', 'KDJ_D', 'KDJ_J',
        'Volatility_10', 'Volume_Change', 'IDX_N225', 'Market_Trend_1D', 
        'Market_Trend_5D', 'Corr_N225_30'
    ]
    
    for col in lag_cols:
        if col in df.columns:
            for lag in range(1, LAG_DAYS + 1):
                df[f'{col}_lag{lag}'] = df[col].shift(lag)
    
    # Open, High, Low のラグも追加
    for col in ['Open', 'High', 'Low']:
        if col in df.columns:
            for lag in range(1, LAG_DAYS + 1):
                df[f'{col}_lag{lag}'] = df[col].shift(lag)
    
    # ★★★ Ticker カラムの追加（最重要）★★★
    if ticker:
        df["Ticker"] = ticker
    
    # NaN削除
    return df.dropna()

# === Feature Column List（学習時と完全一致させる）===
FEATURE_COLS = [
    # Base features
    'Close', 'High', 'Low', 'Open', 'Volume', 'RSI', 'MACD', 'MACD_Signal',
    'ROC_10', 'Vol_Ratio', 'Pct_Change_1D', 'Pct_Change_3D', 'AD_Line', 'AD_Line_ROC',
    'KDJ_D', 'KDJ_J', 'Volatility_10', 'Volume_Change', 'Return_5D', 'Volatility_Ratio',
    'RSI_Change', 'MACD_Hist', 'Volume_Surge',
    'RSI_x_MACD_Hist', 'IDX_N225', 'Market_Trend_1D', 'Market_Trend_5D', 
    'Corr_N225_30', 'Vol_Ratio_x_Market_Trend_5D', 'Raw_Close',
    
    # Ticker（カテゴリ変数）
    'Ticker',
    
    # Lag features for Close, High, Low, Open
    'Close_lag1', 'Close_lag2', 'Close_lag3', 'Close_lag4', 'Close_lag5',
    'High_lag1', 'High_lag2', 'High_lag3', 'High_lag4', 'High_lag5',
    'Low_lag1', 'Low_lag2', 'Low_lag3', 'Low_lag4', 'Low_lag5',
    'Open_lag1', 'Open_lag2', 'Open_lag3', 'Open_lag4', 'Open_lag5',
    
    # Lag features for Volume
    'Volume_lag1', 'Volume_lag2', 'Volume_lag3', 'Volume_lag4', 'Volume_lag5',
    
    # Lag features for technical indicators
    'RSI_lag1', 'RSI_lag2', 'RSI_lag3', 'RSI_lag4', 'RSI_lag5',
    'MACD_lag1', 'MACD_lag2', 'MACD_lag3', 'MACD_lag4', 'MACD_lag5',
    'MACD_Signal_lag1', 'MACD_Signal_lag2', 'MACD_Signal_lag3', 'MACD_Signal_lag4', 'MACD_Signal_lag5',
    'ROC_10_lag1', 'ROC_10_lag2', 'ROC_10_lag3', 'ROC_10_lag4', 'ROC_10_lag5',
    'Vol_Ratio_lag1', 'Vol_Ratio_lag2', 'Vol_Ratio_lag3', 'Vol_Ratio_lag4', 'Vol_Ratio_lag5',
    'Pct_Change_1D_lag1', 'Pct_Change_1D_lag2', 'Pct_Change_1D_lag3', 'Pct_Change_1D_lag4', 'Pct_Change_1D_lag5',
    'Pct_Change_3D_lag1', 'Pct_Change_3D_lag2', 'Pct_Change_3D_lag3', 'Pct_Change_3D_lag4', 'Pct_Change_3D_lag5',
    'AD_Line_ROC_lag1', 'AD_Line_ROC_lag2', 'AD_Line_ROC_lag3', 'AD_Line_ROC_lag4', 'AD_Line_ROC_lag5',
    'KDJ_D_lag1', 'KDJ_D_lag2', 'KDJ_D_lag3', 'KDJ_D_lag4', 'KDJ_D_lag5',
    'KDJ_J_lag1', 'KDJ_J_lag2', 'KDJ_J_lag3', 'KDJ_J_lag4', 'KDJ_J_lag5',
    'Volatility_10_lag1', 'Volatility_10_lag2', 'Volatility_10_lag3', 'Volatility_10_lag4', 'Volatility_10_lag5',
    'Volume_Change_lag1', 'Volume_Change_lag2', 'Volume_Change_lag3', 'Volume_Change_lag4', 'Volume_Change_lag5',
    
    # Lag features for market indicators
    'IDX_N225_lag1', 'IDX_N225_lag2', 'IDX_N225_lag3', 'IDX_N225_lag4', 'IDX_N225_lag5',
    'Market_Trend_1D_lag1', 'Market_Trend_1D_lag2', 'Market_Trend_1D_lag3', 'Market_Trend_1D_lag4', 'Market_Trend_1D_lag5',
    'Market_Trend_5D_lag1', 'Market_Trend_5D_lag2', 'Market_Trend_5D_lag3', 'Market_Trend_5D_lag4', 'Market_Trend_5D_lag5',
    'Corr_N225_30_lag1', 'Corr_N225_30_lag2', 'Corr_N225_30_lag3', 'Corr_N225_30_lag4', 'Corr_N225_30_lag5',
]