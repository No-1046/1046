# -*- coding: utf-8 -*-
"""
全銘柄スキャナー
東証プライム上位銘柄を自動スキャンして上昇確率TOP10を抽出
"""

import sys
import time
import pandas as pd
import yfinance as yf
import joblib
from pathlib import Path
from datetime import datetime
import json

sys.path.append(str(Path(__file__).parent))
from indicators import calculate_indicators

# 設定
MODEL_DIR = Path(__file__).parent
LGBM_PATH = MODEL_DIR / "lgbm_final.pkl"
XGB_PATH = MODEL_DIR / "xgb_final.pkl"
CONFIG_PATH = MODEL_DIR / "model_config.pkl"
RESULTS_PATH = MODEL_DIR / "scan_results.json"

# 東証プライム主要銘柄（時価総額上位 + 流動性高）
PRIME_STOCKS = [
    # 時価総額TOP50程度
    "7203.T", "6758.T", "9984.T", "8306.T", "6501.T",  # トヨタ、ソニー、SBG、三菱UFJ、日立
    "9432.T", "8035.T", "4063.T", "6902.T", "4502.T",  # NTT、東エレク、信越化学、デンソー、武田薬品
    "8316.T", "9433.T", "7741.T", "4543.T", "8001.T",  # 三井住友FG、KDDI、HOYA、テルモ、伊藤忠
    "2914.T", "6861.T", "6367.T", "9020.T", "4568.T",  # JT、キーエンス、ダイキン、JR東日本、第一三共
    "7974.T", "4519.T", "7733.T", "7011.T", "4901.T",  # 任天堂、中外製薬、オリンパス、三菱重工、富士フイルム
    "6273.T", "8031.T", "6954.T", "8058.T", "4005.T",  # SMC、三井物産、ファナック、三菱商事、住友化学
    "5020.T", "9022.T", "7182.T", "6503.T", "8766.T",  # ENEOS、JR東海、ゆうちょ銀行、三菱電機、東京海上
    "6752.T", "7751.T", "3382.T", "4324.T", "9735.T",  # パナソニック、キヤノン、セブン&アイ、電通G、セコム
    "2801.T", "4704.T", "9101.T", "4021.T", "6098.T",  # キッコーマン、トレンドマイクロ、日本郵船、日産化学、リクルート
    "4503.T", "3659.T", "7267.T", "6645.T", "6326.T",  # アステラス製薬、ネクソン、本田技研、オムロン、クボタ
]

# さらに追加可能な中型株
ADDITIONAL_STOCKS = [
    "3825.T", "4755.T", "6920.T", "6981.T", "7012.T",
    "8473.T", "9104.T", "4307.T", "6723.T", "7269.T",
    # ここに追加したい銘柄を入れる
    "4063.T", "6367.T", "4568.T", "7974.T", "6273.T",
    "5020.T", "9022.T", "7182.T", "8766.T", "6752.T",
]

# 東証プライム全銘柄を取得する関数
def get_all_prime_stocks():
    """
    東証プライム全銘柄を取得（約1800銘柄）
    ※実行には数時間かかります
    """
    import pandas as pd
    
    try:
        # JPX（日本取引所グループ）の上場銘柄一覧
        # 更新: 2024年以降の正しいURL
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        
        print("  Downloading stock list from JPX...")
        df = pd.read_excel(url, engine='openpyxl')
        
        # カラム名を確認（実際の名前に合わせる）
        print(f"  Columns: {df.columns.tolist()}")
        
        # 東証プライムのみフィルタ
        if '市場・商品区分' in df.columns:
            prime = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        elif 'Market/Category' in df.columns:
            prime = df[df['Market/Category'].str.contains('Prime', na=False)]
        else:
            # カラム名が違う場合は全部取得
            print("  Warning: Could not filter by market, using all stocks")
            prime = df
        
        # 証券コードに .T を付ける
        if 'コード' in df.columns:
            codes = prime['コード']
        elif 'Code' in df.columns:
            codes = prime['Code']
        else:
            codes = prime.iloc[:, 0]  # 最初の列を使用
        
        tickers = [f"{str(code).strip()}.T" for code in codes if pd.notna(code)]
        
        print(f"✓ Found {len(tickers)} Prime stocks")
        return tickers
        
    except Exception as e:
        print(f"⚠️ Failed to fetch from JPX: {e}")
        print("  Trying alternative method...")
        return get_all_prime_stocks_alternative()

def get_all_prime_stocks_alternative():
    """
    代替方法: 主要な銘柄リストを手動で用意
    """
    # 東証プライム 時価総額上位200銘柄程度
    major_stocks = [
        # 既存のPRIME_STOCKSとADDITIONAL_STOCKSを結合
        *PRIME_STOCKS,
        *ADDITIONAL_STOCKS,
        
        # さらに追加
        "8591.T", "4503.T", "7201.T", "9434.T", "8604.T",
        "6178.T", "4452.T", "2269.T", "4188.T", "3861.T",
        "6702.T", "4911.T", "8801.T", "7974.T", "4528.T",
        "6305.T", "8830.T", "7201.T", "9613.T", "8253.T",
        # ... ここにさらに追加可能
    ]
    
    # 重複削除
    return list(set(major_stocks))

def load_models():
    """モデルをロード"""
    try:
        lgbm = joblib.load(LGBM_PATH)
        xgb = joblib.load(XGB_PATH)
        config = joblib.load(CONFIG_PATH)
        return lgbm, xgb, config
    except Exception as e:
        print(f"❌ Error loading models: {e}")
        return None, None, None

def predict_single_stock(ticker, lgbm, xgb, config, frame='1d'):
    """1銘柄の予測を実行"""
    try:
        # 時間軸に応じて取得期間を調整
        period_map = {
            '1d': '2y',    # 日足: 2年
            '1wk': '5y',   # 週足: 5年
            '1mo': '10y'   # 月足: 10年（データ不足対策）
        }
        period = period_map.get(frame, '2y')
        
        # データ取得
        df = yf.download(ticker, period=period, interval=frame, 
                        auto_adjust=True, progress=False)
        
        if df.empty:
            return None
        
        # データポイント数をチェック
        if len(df) < 50:
            print(f"insufficient data ({len(df)} points)")
            return None
            
        # MultiIndex解消
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 特徴量計算
        feats = calculate_indicators(df, frame=frame, ticker=ticker)
        
        if feats.empty or len(feats) < 10:
            print(f"no features ({len(feats)} rows)")
            return None
        
        # 最新行
        last_row = feats.iloc[[-1]].copy()
        
        # XGBoost用
        base_cols = config['base_features']
        X_xgb = last_row.reindex(columns=base_cols, fill_value=0.0)
        
        # LightGBM用
        all_cols = config['all_features']
        X_lgb = last_row.reindex(columns=all_cols + ['Ticker'], fill_value=0.0)
        X_lgb['Ticker'] = X_lgb['Ticker'].astype('category')
        
        # 予測
        proba_xgb = float(xgb.predict_proba(X_xgb)[0][1])
        proba_lgb = float(lgbm.predict_proba(X_lgb)[0][1])
        
        # アンサンブル
        w_xgb = config.get('w_xgb', 0.6)
        w_lgb = config.get('w_lgb', 0.4)
        proba = w_xgb * proba_xgb + w_lgb * proba_lgb
        
        close = float(feats["Close"].iloc[-1])
        
        # 企業名取得
        try:
            info = yf.Ticker(ticker).get_info()
            name = info.get("shortName") or info.get("longName") or ticker
        except:
            name = ticker
        
        return {
            'ticker': ticker,
            'name': name,
            'prob_up': round(proba, 4),
            'close': close,
            'date': str(feats.index[-1].date()),
        }
        
    except Exception as e:
        print(f"  ⚠️ {ticker}: {str(e)[:50]}")
        return None

def scan_all_stocks(stock_list=None, frame='1d', max_stocks=None, use_all_prime=False, 
                    batch_size=None, resume=False):
    """
    全銘柄をスキャン（バッチ処理対応）
    
    Args:
        stock_list: 銘柄リスト（Noneなら全銘柄）
        frame: 時間軸
        max_stocks: 最大スキャン数（テスト用）
        use_all_prime: Trueなら東証プライム全銘柄を取得
        batch_size: バッチサイズ（中間保存用）
        resume: 前回の続きから再開
    """
    print("=" * 60)
    print(f"Stock Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # モデルロード
    print("\n[1/3] Loading models...")
    lgbm, xgb, config = load_models()
    
    if lgbm is None:
        print("❌ Failed to load models")
        return []
    
    print("✓ Models loaded")
    
    # スキャン対象
    if stock_list is None:
        if use_all_prime:
            print("\n[1.5/3] Fetching all Prime stocks...")
            stock_list = get_all_prime_stocks()
            if stock_list is None:
                print("⚠️ Falling back to default list")
                stock_list = PRIME_STOCKS + ADDITIONAL_STOCKS
        else:
            stock_list = PRIME_STOCKS + ADDITIONAL_STOCKS
    
    if max_stocks:
        stock_list = stock_list[:max_stocks]
    
    print(f"\n[2/3] Scanning {len(stock_list)} stocks...")
    print(f"  Estimated time: {len(stock_list) * 1.5 / 60:.1f} minutes")
    
    # レジューム処理
    results = []
    start_idx = 0
    
    if resume and RESULTS_PATH.exists():
        try:
            with open(RESULTS_PATH, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                results = saved.get('results', [])
                start_idx = len(results)
                print(f"  Resuming from stock #{start_idx + 1}")
        except:
            print("  Could not resume, starting fresh")
    
    # バッチ処理
    for i, ticker in enumerate(stock_list[start_idx:], start_idx + 1):
        print(f"  [{i}/{len(stock_list)}] {ticker}...", end=" ")
        
        result = predict_single_stock(ticker, lgbm, xgb, config, frame)
        
        if result:
            results.append(result)
            print(f"✓ prob={result['prob_up']:.2%}")
        else:
            print("✗ failed")
        
        # レート制限対策
        time.sleep(1)
        
        # バッチ保存
        if batch_size and i % batch_size == 0:
            print(f"\n  💾 Saving intermediate results ({len(results)} stocks)...")
            save_results(results)
            print(f"  ✓ Saved. Continuing...\n")
    
    # ソート
    results.sort(key=lambda x: x['prob_up'], reverse=True)
    
    print(f"\n[3/3] Completed: {len(results)}/{len(stock_list)} stocks analyzed")
    
    return results

def display_top_stocks(results, top_n=10):
    """TOP N銘柄を表示"""
    print("\n" + "=" * 60)
    print(f"🔥 TOP {top_n} STOCKS (上昇確率順)")
    print("=" * 60)
    
    for i, stock in enumerate(results[:top_n], 1):
        signal = "🟢" if stock['prob_up'] >= 0.7 else "🟡" if stock['prob_up'] >= 0.55 else "⚪"
        print(f"{i:2d}. {signal} {stock['ticker']:8s} | "
              f"{stock['name'][:20]:20s} | "
              f"確率: {stock['prob_up']:.2%} | "
              f"終値: ¥{stock['close']:,.0f}")

def save_results(results):
    """結果をJSONで保存"""
    data = {
        'timestamp': datetime.now().isoformat(),
        'count': len(results),
        'results': results
    }
    
    with open(RESULTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Results saved to {RESULTS_PATH}")

def load_latest_results():
    """保存された結果を読み込み"""
    if not RESULTS_PATH.exists():
        return None
    
    try:
        with open(RESULTS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

# コマンドライン実行
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Stock Scanner')
    parser.add_argument('--frame', default='1d', choices=['1d', '1wk', '1mo'],
                       help='Time frame')
    parser.add_argument('--top', type=int, default=10,
                       help='Number of top stocks to display')
    parser.add_argument('--test', type=int,
                       help='Test mode: scan only N stocks')
    parser.add_argument('--all-prime', action='store_true',
                       help='Scan all Prime stocks (~1800 stocks)')
    parser.add_argument('--custom', nargs='+',
                       help='Scan custom list of tickers (e.g., 7203.T 6501.T)')
    parser.add_argument('--csv', type=str,
                       help='Load tickers from CSV file (column: ticker)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Process in batches to save intermediate results')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last saved batch')
    
    args = parser.parse_args()
    
    # カスタムリスト
    stock_list = None
    if args.csv:
        import pandas as pd
        try:
            csv_df = pd.read_csv(args.csv)
            if 'ticker' not in csv_df.columns:
                print(f"❌ CSV must have a 'ticker' column. Found: {csv_df.columns.tolist()}")
                exit(1)
            stock_list = csv_df['ticker'].tolist()
            print(f"✓ Loaded {len(stock_list)} stocks from {args.csv}")
        except FileNotFoundError:
            print(f"❌ File not found: {args.csv}")
            exit(1)
        except Exception as e:
            print(f"❌ Error loading CSV: {e}")
            exit(1)
    elif args.custom:
        stock_list = args.custom
        print(f"Using custom list: {len(stock_list)} stocks")
    
    # スキャン実行
    results = scan_all_stocks(
        stock_list=stock_list,
        frame=args.frame,
        max_stocks=args.test,
        use_all_prime=args.all_prime,
        batch_size=args.batch_size,
        resume=args.resume
    )
    
    if results:
        # TOP表示
        display_top_stocks(results, top_n=args.top)
        
        # 保存
        save_results(results)
    else:
        print("❌ No results")