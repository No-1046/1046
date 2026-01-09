import os
import glob
import json
import argparse
import pandas as pd
import google.generativeai as genai
from datetime import datetime
import traceback

# ==========================================
# ★ここにAPIキーを直接入れてください
# ==========================================
API_KEY = os.environ.get("GEMINI_API_KEY")  # あなたのキーを維持してください

# ==========================================
# 修正箇所: analyze_sentiment 関数をこれに置き換えてください
# ==========================================
def analyze_sentiment(text, model):
    # プロンプト（指示文）
    prompt = f"""
    あなたは熟練したニュースアナリストです。
    以下のニュース記事の内容が持つ「社会的・経済的な影響」に基づき、感情分析を行ってください。

    # 評価基準
    - スコア範囲: -1.0 (非常にネガティブ/損失/悲劇) 〜 1.0 (非常にポジティブ/利益/発展)
    - 0.0は完全な中立、または事実の羅列のみの場合。

    # 制約事項
    - 出力は純粋なJSON形式のみとし、Markdown記法（```json等）や挨拶文は一切含めないでください。
    - reasonは、なぜそのスコアになったのか、具体的な要因（例：業績悪化、新技術の発見など）を含めて簡潔に記述してください。

    # ニュース
    {text}

    # 出力形式
    {{"score": float, "reason": "string"}}
    """
    
    try:
        response = model.generate_content(prompt)
        txt = response.text
        
        # JSON部分を探す
        start = txt.find('{')
        end = txt.rfind('}') + 1
        if start == -1 or end == -1:
            print(f"  [API Warning] JSONが見つかりません。返答: {txt[:50]}...")
            return {"score": 0, "reason": "JSON Parse Error"}
            
        return json.loads(txt[start:end])
        
    except Exception as e:
        # ★ここでエラーの正体を表示する！
        print(f"  [API ERROR] {e}")
        return {"score": 0, "reason": str(e)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--use-gemini", action="store_true")
    parser.add_argument("--filter-lowimpact", action="store_true")
    args = parser.parse_args()

    print("--- 分析開始 (Debug Ver) ---")
    
    # ファイル検索 (today_*.csv 対応)
    csv_files = glob.glob(os.path.join(args.input, "news_*.csv"))
    if not csv_files:
        csv_files = glob.glob(os.path.join(args.input, "today_*.csv"))
    if not csv_files:
        csv_files = glob.glob(os.path.join(args.base, "today_*.csv"))
    
    if not csv_files:
        print(f"エラー: ニュースCSVが見つかりません。パス: {args.input}")
        return

    target_csv = sorted(csv_files)[-1]
    # UTF-8 with BOM 対応
    df = pd.read_csv(target_csv, encoding='utf-8-sig')
    print(f"Target: {target_csv} ({len(df)}件)")

    # 列名の揺らぎ吸収
    title_col = "title"
    if "newstitle" in df.columns: title_col = "newstitle"
    
    url_col = "url"
    if "newslink" in df.columns: url_col = "newslink"
        
    date_col = "published_date"
    if "tradedate" in df.columns: date_col = "tradedate"

    # Gemini設定
    if API_KEY and "AIza" in API_KEY:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        print("Gemini API: ON")
    else:
        print("Gemini API: OFF (Keyが無効です)")
        model = None

    results = []

    for index, row in df.iterrows():
        title = str(row.get(title_col, ""))
        print(f"[{index+1}/{len(df)}] Analyzing: {title[:15]}...")
        
        if model:
            res = analyze_sentiment(title, model)
            score = res.get("score", 0)
            reason = res.get("reason", "")
        else:
            score = 0
            reason = "No API"
        
        # 結果を表示（0点なら理由も表示）
        print(f"  -> Score: {score} (Reason: {reason})")
        
        results.append({
            "date": row.get(date_col, datetime.now().strftime("%Y-%m-%d")),
            "title": title,
            "url": row.get(url_col, ""),
            "sentimentscore": score,
            "reason": reason
        })

    out_dir = os.path.join(args.base, "history_csv")
    os.makedirs(out_dir, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(out_dir, f"history_append_{today}.csv")

    print(f"保存先: {out_path}")
    pd.DataFrame(results).to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"✓ 保存完了: {out_path}")
    
if __name__ == "__main__":
    main()