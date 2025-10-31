# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import yfinance as yf


# ========== Utility ==========
def tz_naive_index(df):
    return df.tz_localize(None) if df.index.tz is not None else df


# ========== Feature Engineering Core ==========
def calculate_indicators(df: pd.DataFrame, frame: str = "1d") -> pd.DataFrame:
    df = df.copy()
    df = tz_naive_index(df)
    df = df.sort_index()
    
    # --- Basic ----
    df["Raw_Close"] = df["Close"]
    df["Pct_Change_1D"] = df["Close"].pct_change()
    df["Pct_Change_3D"] = df["Close"].pct_change(3)

    # Volume sometimes missing
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    df["Volume_Change"] = df["Volume"].pct_change()

    # RSI (14)
    delta = df["Close"].diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = -delta.clip(upper=0).rolling(14).mean()
    rs = up / down
    df["RSI"] = 100 - (100 / (1 + rs))

    # ROC10
    df["ROC_10"] = df["Close"].pct_change(10)

    # MACD
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # KDJ (Stochastics)
    low9 = df["Low"].rolling(9).min()
    high9 = df["High"].rolling(9).max()
    df["KDJ_D"] = ((df["Close"] - low9) / (high9 - low9)).ewm(span=3).mean()
    df["KDJ_J"] = 3 * df["KDJ_D"] - 2 * df["KDJ_D"].rolling(3).mean()

    # Volatility
    df["Volatility_10"] = df["Pct_Change_1D"].rolling(10).std()
    df["Volatility_Ratio"] = df["Volatility_10"] / df["Volatility_10"].rolling(20).mean()

    # Volume indicators
    df["Vol_Ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    df["Volume_Surge"] = (df["Vol_Ratio"] > 2.0).astype(int)


    # Return horizon
    df["Return_5D"] = df["Close"].pct_change(5)

    # RSI change
    df["RSI_Change"] = df["RSI"].diff()

    # AD Line (簡易)
    df["AD_Line"] = (df["Close"] - df["Low"] - (df["High"] - df["Close"])) / \
                    (df["High"] - df["Low"]).replace(0, np.nan)
    df["AD_Line"] = df["AD_Line"].cumsum()
    df["AD_Line_ROC"] = df["AD_Line"].pct_change()

    # --- Market Indicators (N225 ＋ 金利) ---
    try:
        n225 = yf.download("^N225", period="2y", interval=frame, auto_adjust=True, progress=False)
        n225 = tz_naive_index(n225)
        df["IDX_N225"] = n225["Close"]
        df["Market_Trend_1D"] = n225["Close"].pct_change()
        df["Market_Trend_5D"] = n225["Close"].pct_change(5)
        df["Corr_N225_30"] = df["Close"].rolling(30).corr(n225["Close"])
    except Exception:
        df["IDX_N225"] = 0.0
        df["Market_Trend_1D"] = 0.0
        df["Market_Trend_5D"] = 0.0
        df["Corr_N225_30"] = 0.0

    try:
        tnx = yf.download("^TNX", period="2y", interval=frame, auto_adjust=True, progress=False)
        tnx = tz_naive_index(tnx)
        df["TNX_Change_1D"] = tnx["Close"].pct_change()
        df["TNX_Change_5D"] = tnx["Close"].pct_change(5)
    except Exception:
        df["TNX_Change_1D"] = 0.0
        df["TNX_Change_5D"] = 0.0

    # Cross
    df["RSI_x_MACD_Hist"] = df["RSI"] * df["MACD_Hist"]
    df["Vol_Ratio_x_Market_Trend_5D"] = df["Vol_Ratio"] * df["Market_Trend_5D"]

    return df.dropna()


# === Feature Column List ===
FEATURE_COLS = [
    'Close', 'High', 'Low', 'Open', 'Volume', 'RSI', 'MACD', 'MACD_Signal',
    'ROC_10', 'Vol_Ratio', 'Pct_Change_1D', 'Pct_Change_3D', 'AD_Line', 'AD_Line_ROC',
    'KDJ_D', 'KDJ_J', 'Volatility_10', 'Volume_Change', 'Return_5D', 'Volatility_Ratio',
    'RSI_Change', 'MACD_Hist', 'Volume_Surge', 'Vol_Ticker_Ratio',
    'RSI_x_MACD_Hist', 'IDX_N225', 'Market_Trend_1D', 'Market_Trend_5D', 'TNX_Change_1D',
    'TNX_Change_5D', 'Corr_N225_30', 'Vol_Ratio_x_Market_Trend_5D', 'Raw_Close'
]
