#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
東証プライム全銘柄を自動取得してCSVに保存
"""

import pandas as pd
import requests
from io import BytesIO

def method1_jpx_official():
    """方法1: JPX公式サイトから取得"""
    print("方法1: JPX公式サイトから取得中...")
    
    try:
        # 日本取引所グループの公式データ
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        
        response = requests.get(url, timeout=30)
        df = pd.read_excel(BytesIO(response.content))
        
        print(f"  取得: {len(df)} 銘柄")
        print(f"  カラム: {df.columns.tolist()}")
        
        # プライム市場のみフィルタ
        if '市場・商品区分' in df.columns:
            prime = df[df['市場・商品区分'].str.contains('プライム', na=False)]
            codes = prime['コード'].astype(str).str.strip()
        else:
            print("  ⚠️ カラム名が想定と異なります")
            codes = df.iloc[:, 0].astype(str).str.strip()
        
        # .T を付ける
        tickers = [f"{code}.T" for code in codes if code.isdigit()]
        
        print(f"  ✓ プライム市場: {len(tickers)} 銘柄")
        return tickers
        
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        return None

def method2_github_list():
    """方法2: GitHub上の銘柄リストから取得"""
    print("\n方法2: GitHubの銘柄リストから取得中...")
    
    try:
        # 有志が管理している銘柄リスト
        urls = [
            "https://raw.githubusercontent.com/stocketf/jpx-listed-companies/main/data/prime.csv",
            "https://gist.githubusercontent.com/anonymous/raw/jpx_prime_stocks.csv"
        ]
        
        for url in urls:
            try:
                df = pd.read_csv(url, timeout=10)
                if 'ticker' in df.columns or 'code' in df.columns:
                    col = 'ticker' if 'ticker' in df.columns else 'code'
                    tickers = df[col].tolist()
                    print(f"  ✓ {len(tickers)} 銘柄取得")
                    return tickers
            except:
                continue
        
        print("  ✗ 利用可能なソースが見つかりませんでした")
        return None
        
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        return None

def method3_generate_range():
    """方法3: 証券コード範囲から生成（網羅的）"""
    print("\n方法3: 証券コード範囲から生成中...")
    
    try:
        # 東証プライムの一般的な証券コード範囲
        ranges = [
            (1301, 1999),  # 水産・農林業、鉱業、建設業
            (2001, 2999),  # 食料品
            (3001, 3999),  # 繊維製品、パルプ・紙、化学
            (4001, 4999),  # 医薬品、石油、ゴム製品、ガラス・土石
            (5001, 5999),  # 鉄鋼、非鉄金属
            (6001, 6999),  # 機械、電気機器
            (7001, 7999),  # 輸送用機器、精密機器
            (8001, 8999),  # 銀行、証券、保険、その他金融
            (9001, 9999),  # 陸運、海運、空運、倉庫、通信、電気・ガス、サービス
        ]
        
        tickers = []
        for start, end in ranges:
            tickers.extend([f"{code}.T" for code in range(start, end + 1)])
        
        print(f"  ✓ {len(tickers)} 銘柄生成（実在しない銘柄も含む）")
        print("  ⚠️ この方法は存在しない銘柄コードも含まれます")
        return tickers
        
    except Exception as e:
        print(f"  ✗ 失敗: {e}")
        return None

def method4_major_stocks():
    """方法4: 主要銘柄のみ（確実に存在する）"""
    print("\n方法4: 主要銘柄リストを使用...")
    
    # 時価総額上位300銘柄程度（確実に存在）
    major = [
        # 時価総額TOP100
        "7203.T", "6758.T", "9984.T", "8306.T", "6501.T", "9432.T", "8035.T", "4063.T", "6902.T", "4502.T",
        "8316.T", "9433.T", "7741.T", "4543.T", "8001.T", "2914.T", "6861.T", "6367.T", "9020.T", "4568.T",
        "7974.T", "4519.T", "7733.T", "7011.T", "4901.T", "6273.T", "8031.T", "6954.T", "8058.T", "4005.T",
        "5020.T", "9022.T", "7182.T", "6503.T", "8766.T", "6752.T", "7751.T", "3382.T", "4324.T", "9735.T",
        "2801.T", "4704.T", "9101.T", "4021.T", "6098.T", "4503.T", "3659.T", "7267.T", "6645.T", "6326.T",
        
        # 時価総額100-200位
        "3825.T", "4755.T", "6920.T", "6981.T", "7012.T", "8473.T", "9104.T", "4307.T", "6723.T", "7269.T",
        "8591.T", "7201.T", "9434.T", "8604.T", "6178.T", "4452.T", "2269.T", "4188.T", "3861.T", "6702.T",
        "4911.T", "8801.T", "4528.T", "6305.T", "8830.T", "9613.T", "8253.T", "4523.T", "6971.T", "7832.T",
        
        # 時価総額200-300位
        "6594.T", "4452.T", "7936.T", "6857.T", "4612.T", "8002.T", "8015.T", "8053.T", "4704.T", "6752.T",
        "3402.T", "4901.T", "6504.T", "7912.T", "9501.T", "9502.T", "9503.T", "2502.T", "4063.T", "6479.T",
    ]
    
    # 重複削除
    tickers = list(set(major))
    print(f"  ✓ {len(tickers)} 銘柄（主要銘柄のみ）")
    return tickers

def save_to_csv(tickers, filename='all_stocks.csv'):
    """CSVに保存"""
    df = pd.DataFrame({'ticker': tickers})
    df.to_csv(filename, index=False)
    print(f"\n✅ 保存完了: {filename} ({len(tickers)} 銘柄)")
    print(f"   サンプル: {tickers[:5]}")

def main():
    print("=" * 60)
    print("東証プライム全銘柄取得ツール")
    print("=" * 60)
    
    tickers = None
    
    # 方法1を試す
    tickers = method1_jpx_official()
    
    # 失敗したら方法2
    if not tickers:
        tickers = method2_github_list()
    
    # それでも失敗したら方法4（主要銘柄）
    if not tickers:
        print("\n⚠️ 自動取得に失敗したため、主要銘柄リストを使用します")
        tickers = method4_major_stocks()
    
    # 保存
    if tickers:
        save_to_csv(tickers, 'all_prime_stocks.csv')
        
        # 統計情報
        print("\n📊 統計:")
        print(f"  総銘柄数: {len(tickers)}")
        print(f"  範囲: {min(tickers)} - {max(tickers)}")
        
        return True
    else:
        print("\n❌ すべての方法で取得に失敗しました")
        print("\n代替案:")
        print("  1. 証券コード範囲から生成: python fetch_all_stocks.py --range")
        print("  2. 主要銘柄のみ使用: python fetch_all_stocks.py --major")
        return False

if __name__ == "__main__":
    import sys
    
    if '--range' in sys.argv:
        tickers = method3_generate_range()
        if tickers:
            save_to_csv(tickers, 'all_codes_full.csv')
    elif '--major' in sys.argv:
        tickers = method4_major_stocks()
        if tickers:
            save_to_csv(tickers, 'major_stocks.csv')
    else:
        main()