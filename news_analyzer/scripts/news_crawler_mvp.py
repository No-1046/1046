# -*- coding: utf-8 -*-
"""
Google News RSS クローラー — 任意企業対応版
- company + ticker を受け取り、その会社向けのニュースのみ抽出
- 直近 N 日を today_YYYYMMDD.csv に日次分割出力
- BASE は NIN_PROJECT_BASE（app.py が会社別フォルダを設定）
"""
import os, json, hashlib, time, argparse, re
from datetime import datetime, timedelta, timezone, date
from urllib.parse import quote, urlparse, urlsplit, urlunsplit, parse_qsl

import requests
import feedparser
import pandas as pd

# yfinance 後端：避免 curl_cffi
os.environ.setdefault("YF_USE_CURL_CFFI", "0")
import yfinance as yf

from bs4 import BeautifulSoup
from dateutil import parser as dtparser, relativedelta

# ---------- BASE ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE       = os.environ.get("NIN_PROJECT_BASE", SCRIPT_DIR)
TODAY_DIR  = os.path.join(BASE, "today_csv")
HIST_DIR   = os.path.join(BASE, "history_csv")
os.makedirs(TODAY_DIR, exist_ok=True)
os.makedirs(HIST_DIR,  exist_ok=True)

COL_DATE   = "tradedate"
COL_TITLE  = "newstitle"
COL_CLOSE  = "closeprice"

SEEN_PATH  = os.path.join(HIST_DIR, "seen_news_ids.json")
STATE_PATH = os.path.join(HIST_DIR, "last_crawled.txt")

# ---------- 雜項 ----------
UA  = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/2.1)"}
JST = timezone(timedelta(hours=9))

# 一些常見公司的日/英別名（可自行擴充）
COMPANY_SYNONYMS = {
    "任天堂": ["任天堂", "Nintendo", "Nintendo Co., Ltd."],
    "ソニー": ["ソニー", "Sony", "Sony Group", "ソニーグループ"],
    "カプコン": ["カプコン", "CAPCOM", "Capcom"],
    "スクウェア・エニックス": ["スクウェア・エニックス", "スクエニ", "Square Enix"],
    "バンダイナムコ": ["バンダイナムコ", "Bandai Namco", "BANDAI NAMCO"],
    "セガ": ["セガ", "SEGA"],
}

# 低影響/雜訊關鍵字（保留）
BAD_PATTERNS = [
    "VTuber","Vtuber","アイドル","実況","配信","生配信","切り抜き",
    "ファンアート","同人","カード","トレカ","大会","イベント出演",
    "カジノ","パチンコ","スロット","スキャンダル","炎上","ガチャ",
    "非公式","MOD","コスプレ","同梱特典","ライブ配信","攻略動画",
    "YouTube","ユーチューバー","歌ってみた","踊ってみた","声優","配信者",
    "ゲーム実況","生放送","Twitch","グッズ","コラボカフェ"
]

USE_SOURCE_WHITELIST = False
SOURCE_WHITELIST = {
    "www3.nhk.or.jp","www.nikkei.com","xtech.nikkei.com","toyokeizai.net",
    "jp.reuters.com","www.reuters.com","www.asahi.com","mainichi.jp",
    "www.yomiuri.co.jp","www.jiji.com","www.itmedia.co.jp","www.watch.impress.co.jp",
    "kabutan.jp","kabuyoho.ifis.co.jp","www.bloomberg.co.jp","www.bloomberg.com",
    "www.wsj.com","www.marketwatch.com","finance.yahoo.co.jp",
    "www.famitsu.com","automaton-media.com","www.4gamer.net","www.gamespark.jp"
}

# ---------- 工具 ----------
def jst_now(): return datetime.now(JST)
def to_jst(dt: datetime):
    if dt.tzinfo is None: return dt.replace(tzinfo=JST)
    return dt.astimezone(JST)
def parse_dt_safe(s):
    try: return dtparser.parse(s)
    except Exception: return None
def is_on_date_jst_or_prev(dt: datetime, target: date) -> bool:
    d = to_jst(dt).date()
    return (d == target) or (d == (target - timedelta(days=1)))
def _id(title: str, link: str) -> str:
    raw = (title or "").strip() + "||" + (link or "")
    return hashlib.md5(raw.encode("utf-8","ignore")).hexdigest()

def _load_seen() -> set:
    if os.path.exists(SEEN_PATH):
        try:
            return set(json.load(open(SEEN_PATH,"r",encoding="utf-8")))
        except Exception:
            return set()
    return set()

def _save_seen(seen: set):
    try:
        json.dump(sorted(list(seen)), open(SEEN_PATH,"w",encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass

def fetch_rss(url: str, retry: int = 3, timeout: int = 10):
    for i in range(retry):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.raise_for_status()
            return feedparser.parse(r.text)
        except Exception:
            if i == retry - 1:
                return feedparser.parse("")
            time.sleep(0.8)

def fetch_meta_desc(url: str) -> str:
    if not url: return ""
    try:
        r = requests.get(url, headers=UA, timeout=6)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        m = soup.find("meta", attrs={"name": "description"}) \
            or soup.find("meta", attrs={"property": "og:description"})
        return (m.get("content") or "").strip() if m else ""
    except Exception:
        return ""

def build_rss_url(q: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(q)}&hl=ja&gl=JP&ceid=JP:ja"

def host_in_whitelist(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        return any(host == d or host.endswith("." + d) for d in SOURCE_WHITELIST)
    except Exception:
        return False

def build_company_keywords(company: str, ticker: str):
    # 取數字代碼（例：6758.T → 6758）
    code = re.sub(r"\D","", ticker or "")
    t_list = [ticker] if ticker else []
    if code: t_list += [code]

    # 同義詞
    syns = COMPANY_SYNONYMS.get(company, [])
    # 自己也加進去
    if company not in syns: syns = [company] + syns

    # 去重
    syns = list(dict.fromkeys([s for s in syns if s and isinstance(s,str)]))

    # 查詢關鍵詞（精確＋常見財經詞）
    queries = []
    for s in syns + t_list:
        if not s: continue
        queries += [
            f"\"{s}\"", f"\"{s} 株価\"", f"\"{s} 株式\"", f"\"{s} 決算\"",
            f"\"{s} earnings\"", f"\"{s} stock\""
        ]
    # 必須包含的關鍵詞
    must_include = syns + t_list
    return queries, must_include


# ---- yfinance 用 ticker 候補生成（防止沒抓到股價） ----
def _ticker_candidates_for_yf(ticker: str):
    """
    yfinance 用の ticker 候補をいくつか生成する。
    例:
      "6758"      -> ["6758", "6758.T"]
      "6758.T"    -> ["6758.T", "6758"]
      "SONY"      -> ["SONY"]
    """
    ticker = (ticker or "").strip()
    cands = []
    if ticker:
        cands.append(ticker)

    code = re.sub(r"\D", "", ticker)  # 數字部分だけ
    if code and code not in cands:
        cands.append(code)
    # 日本株っぽい 4 ケタコードなら ".T" を付けた候補も追加
    if code and len(code) == 4:
        alt = f"{code}.T"
        if alt not in cands:
            cands.append(alt)

    # 去重保持順序
    return list(dict.fromkeys(cands))


def build_close_map(ticker: str, start_d: date, end_d: date) -> dict:
    """
    指定期間の終値を yfinance から取得して {date: Close} の dict にする。
    - ticker がちょっと違っても良いように、候補をいくつか試す
    - 全部ダメだった場合は空 dict を返し、あとで daily 集計側で前日終値を補間する
    """
    start_pad = (start_d - timedelta(days=10)).isoformat()
    end_pad   = (end_d + timedelta(days=3)).isoformat()

    candidates = _ticker_candidates_for_yf(ticker)
    last_err = None
    for tk in candidates:
        try:
            t = yf.Ticker(tk)
            hist = t.history(start=start_pad, end=end_pad, interval="1d")
            if hist is None or hist.empty:
                continue
            hist = hist.dropna()
            if hist.empty:
                continue
            if tk != ticker:
                print(f"[INFO] yfinance: '{ticker}' では株価が取れなかったため、"
                      f"'{tk}' を使用して {len(hist)} 日分の株価を取得しました。")
            return {pd.to_datetime(ix).date(): float(row["Close"]) for ix, row in hist.iterrows()}
        except Exception as e:
            last_err = e
            continue

    # ここまで来ると株価は取得できなかった
    msg = f"[WARN] yfinance 無法取得股價（嘗試 ticker 候選 {candidates}）。將以空 closeprice 繼續。"
    if last_err is not None:
        msg += f" 最後錯誤: {last_err}"
    print(msg)
    return {}


def strip_tracking_params(url: str) -> str:
    try:
        parts = urlsplit(url)
        qs = [(k,v) for (k,v) in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
        new_query = "&".join([f"{k}={v}" for k,v in qs]) if qs else ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return ""

def is_target_company_news(title: str, desc: str, link: str, must_words: list) -> bool:
    if not title: return False
    t_l = title.lower(); d_l = (desc or "").lower()
    for bad in BAD_PATTERNS:
        if bad.lower() in t_l: return False
    # 必須包含其中一詞（標題或描述命中）
    for kw in must_words:
        k = kw.lower()
        if (k in t_l) or (k in d_l):
            if USE_SOURCE_WHITELIST:
                return host_in_whitelist(link)
            return True
    return False

# ---------- 主流程 ----------
def crawl_one_day(target_day: date, ignore_seen_global: bool, queries: list, must_words: list):
    seen_global = _load_seen() if (not ignore_seen_global) else set()
    seen_day = set()
    rows = []
    stats_scanned = 0
    stats_after_date = 0
    stats_after_filter = 0

    for q in queries:
        feed = fetch_rss(build_rss_url(q))
        for e in (feed.entries or []):
            stats_scanned += 1
            ts = e.get("published") or e.get("updated") or e.get("pubDate")
            dt = parse_dt_safe(ts) if ts else jst_now()
            if not is_on_date_jst_or_prev(dt, target_day):  # 僅取當天/前夜
                continue
            stats_after_date += 1

            title = (e.get("title") or "").strip()
            link  = strip_tracking_params((e.get("link")  or "").strip())
            if not title or not link: continue

            desc  = fetch_meta_desc(link)
            if not is_target_company_news(title, desc, link, must_words):
                continue
            stats_after_filter += 1

            hid = _id(title, link)
            if hid in seen_day: continue
            if (not ignore_seen_global) and (hid in seen_global): continue

            rows.append({
                "hid": hid, "title": title, "link": link, "desc": desc,
                "published_jst": to_jst(parse_dt_safe(ts) if ts else jst_now()).strftime("%Y-%m-%d %H:%M:%S%z"),
            })
            seen_day.add(hid)
        time.sleep(0.25)

    if rows and (not ignore_seen_global):
        seen_global.update(r["hid"] for r in rows)
        _save_seen(seen_global)

    rows.sort(key=lambda r: r["published_jst"])
    print(f"[INFO] 掃描統計：RSS總件數={stats_scanned}、日期過濾後={stats_after_date}、公司關聯過濾後={stats_after_filter}、最終件數={len(rows)}")
    return rows

def run_for_period(since_d: date, until_d: date, ignore_seen_global: bool, overwrite: bool, company: str, ticker: str):
    queries, must_words = build_company_keywords(company, ticker)
    close_map = build_close_map(ticker, since_d, until_d)

    if not close_map:
        print(f"[WARN] {since_d} ~ {until_d} 期間內股價資料為空（ticker={ticker}）。"
              f"today_csv 的 closeprice 將留空，之後在日次集計時會以前一日股價自動補齊。")

    cur = since_d
    total_days = 0
    total_rows = 0
    while cur <= until_d:
        out = os.path.join(TODAY_DIR, f"today_{cur.strftime('%Y%m%d')}.csv")
        if os.path.exists(out) and not overwrite:
            print(f"[SKIP] {cur} 已存在，跳過 ({out})")
            cur += timedelta(days=1); total_days += 1
            continue

        rows = crawl_one_day(cur, ignore_seen_global=ignore_seen_global, queries=queries, must_words=must_words)
        tradedate = None; close = None
        if close_map:
            d = cur
            for _ in range(10):
                if d in close_map:
                    tradedate, close = d.isoformat(), close_map[d]; break
                d = d - timedelta(days=1)

        if rows:
            df = pd.DataFrame({
                COL_DATE:   [tradedate or cur.isoformat()] * len(rows),
                COL_TITLE:  [r['title'] for r in rows],
                COL_CLOSE:  [close if close is not None else ""] * len(rows),
                "newslink":      [r['link'] for r in rows],
                "published_jst": [r['published_jst'] for r in rows],
                "newsdesc":      [r['desc'] for r in rows],
            })
            df.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"[OK] {cur} 的新聞 {len(df)} 筆已輸出：{out}")
            total_rows += len(df)
        else:
            print(f"[INFO] {cur} 無符合新聞，略過。")

        total_days += 1
        cur += timedelta(days=1)

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        f.write(until_d.isoformat())

    print(f"\n[DONE] 完成範圍：{since_d} ~ {until_d}  天數={total_days}  累計新聞數={total_rows}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--company", required=True, type=str, help="公司名稱（例：ソニー、任天堂…）")
    p.add_argument("--ticker",  required=True, type=str, help="股票代碼（例：6758.T、7974.T）")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--use-source-whitelist", action="store_true")
    p.add_argument("--date", type=str)
    p.add_argument("--since", type=str)
    p.add_argument("--until", type=str)
    p.add_argument("--last-ndays", type=int)
    args = p.parse_args()

    global USE_SOURCE_WHITELIST
    if args.use_source_whitelist:
        USE_SOURCE_WHITELIST = True
        print("[OK] 已啟用來源網域白名單模式。")

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        run_for_period(d, d, ignore_seen_global=False, overwrite=args.overwrite,
                       company=args.company, ticker=args.ticker); return
    if args.since or args.until:
        if not (args.since and args.until):
            raise SystemExit("錯誤：--since 與 --until 需成對使用。")
        s = datetime.strptime(args.since, "%Y-%m-%d").date()
        u = datetime.strptime(args.until, "%Y-%m-%d").date()
        if s > u: s, u = u, s
        run_for_period(s, u, ignore_seen_global=False, overwrite=args.overwrite,
                       company=args.company, ticker=args.ticker); return
    if args.last_ndays:
        today = jst_now().date()
        since = today - timedelta(days=int(args.last_ndays))
        run_for_period(since, today, ignore_seen_global=False, overwrite=args.overwrite,
                       company=args.company, ticker=args.ticker); return

    # 預設抓「近一個月」
    today = jst_now().date()
    since = today - relativedelta.relativedelta(months=1)
    run_for_period(since, today, ignore_seen_global=False, overwrite=args.overwrite,
                   company=args.company, ticker=args.ticker)

if __name__ == "__main__":
    main()
