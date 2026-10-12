
import argparse, csv, hashlib, json, os, re, time
from datetime import datetime
from urllib.parse import quote_plus

import feedparser
import requests

# ---------- Settings ----------
SEARCH_QUERIES = [
    "AI tool launch",
    "launches new AI model",
    "introduces AI assistant",
    "new AI app released",
    "AI startup unveils",
    "OpenAI OR Anthropic OR Google OR Meta OR Mistral launches",
    "Product Hunt AI tool",
]

EXTRA_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://hnrss.org/newest?q=AI+launch&points=30",   # Hacker News
]

LAUNCH_WORDS = re.compile(
    r"\b(launch(es|ed)?|releas(es|ed)?|unveil(s|ed)?|introduc(es|ed)?|"
    r"announc(es|ed)?|debut(s|ed)?|rolls? out|rolled out|now available|"
    r"open[- ]sourc(es|ed)|beta)\b", re.I)

AI_WORDS = re.compile(
    r"\b(AI|A\.I\.|GPT|LLM|chatbot|agent|copilot|model|generative|"
    r"machine learning|assistant|diffusion)\b", re.I)

SEEN_FILE = "seen_launches.json"
OUT_CSV = "ai_launches.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AILaunchBot/1.0)"}


# ---------- Fetch ----------
def google_news_feed(query, when="1d", lang="en", country="US"):
    q = f"{query} when:{when}"
    return (f"https://news.google.com/rss/search?q={quote_plus(q)}"
            f"&hl={lang}-{country}&gl={country}&ceid={country}:{lang}")


def parse_feed(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        return feedparser.parse(resp.content).entries
    except Exception as e:
        print(f"[warn] feed fail: {url[:70]}... ({e})")
        return []


def collect():
    urls = [google_news_feed(q) for q in SEARCH_QUERIES] + EXTRA_FEEDS
    items = []
    for u in urls:
        for e in parse_feed(u):
            items.append({
                "title": re.sub(r"\s+", " ", e.get("title", "")).strip(),
                "link": e.get("link", ""),
                "source": (e.get("source", {}) or {}).get("title") or u.split("/")[2],
                "published": e.get("published", ""),
            })
        time.sleep(1)  # site ke bishi chap na dewar jonno
    return items


# ---------- Filter / Clean ----------
def is_launch_news(item):
    t = item["title"]
    return bool(LAUNCH_WORDS.search(t) and AI_WORDS.search(t))


def key(item):
    norm = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:80]
    return hashlib.md5(norm.encode()).hexdigest()


def guess_tool_name(title):
    """Title theke possible tool/company naam anumaan kora (simple heuristic)."""
    m = re.findall(r"\b([A-Z][A-Za-z0-9\-\.]+(?:\s[A-Z0-9][A-Za-z0-9\-\.]+)?)", title)
    skip = {"AI", "The", "New", "How", "Why", "What", "Is", "A"}
    m = [x for x in m if x not in skip]
    return m[0] if m else ""


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)


# ---------- Output ----------
def append_csv(rows):
    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["found_at", "tool_guess", "title", "source", "published", "link"])
        if new_file:
            w.writeheader()
        w.writerows(rows)


def telegram(text):
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": False},
                      timeout=15)
    except Exception as e:
        print("[warn] telegram fail:", e)


# ---------- Main ----------
def run_once():
    seen = load_seen()
    fresh, rows = [], []
    for it in collect():
        if not is_launch_news(it):
            continue
        k = key(it)
        if k in seen:
            continue
        seen.add(k)
        it["tool_guess"] = guess_tool_name(it["title"])
        it["found_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        fresh.append(it)
        rows.append(it)

    if rows:
        append_csv(rows)
        save_seen(seen)

    print(f"\n=== {len(fresh)} ta notun AI launch news ===")
    for it in fresh:
        print(f"- [{it['tool_guess'] or '?'}] {it['title']}\n  {it['source']} | {it['link']}")
        telegram(f"🚀 {it['title']}\n{it['source']}\n{it['link']}")
    return fresh


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, default=0, help="minute interval (0 = ekbar run)")
    args = ap.parse_args()

    if args.watch:
        while True:
            run_once()
            print(f"\n{args.watch} minute pore abar check hobe... (Ctrl+C diye bondho)")
            time.sleep(args.watch * 60)
    else:
        run_once()