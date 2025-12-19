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
    ニュースの感情分析を行い、-1.0(ネガティブ)〜1.0(ポジティブ)のスコアをつけてください。
    ニュース: {text}
    回答はJSONのみ: {{"score": 0.5, "reason": "..."}}
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

    # 修正前（削除またはコメントアウト）:
    # base_fixed = args.base.replace("news_analyzer\\", "").replace("news_analyzer/", "")
    # if "companies" not in base_fixed: 
    #      base_fixed = os.path.join("companies", os.path.basename(args.base.rstrip("\\/")))

    # 修正後（シンプルにする）=正しいディレクトリに保存されなかったため:
    base_fixed = args.base
    out_dir = os.path.join(base_fixed, "history_csv")
    os.makedirs(out_dir, exist_ok=True)
    
    today = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(out_dir, f"history_append_{today}.csv")
    
    pd.DataFrame(results).to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"保存完了: {out_path}")

if __name__ == "__main__":
    main()