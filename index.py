"""
Top 15 valuable Python snippets: Google News / Google Trends / RSS scraping + publish ideas
Install: pip install feedparser requests beautifulsoup4 trafilatura
"""
import csv, json, re, hashlib
from collections import Counter
from urllib.parse import quote_plus, urljoin
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RSSBot/1.0)"}


# 1. Google News: keyword search feed
def google_news(query, lang="en", country="BD", when=None):
    q = f"{query} when:{when}" if when else query
    url = (f"https://news.google.com/rss/search?q={quote_plus(q)}"
           f"&hl={lang}-{country}&gl={country}&ceid={country}:{lang}")
    feed = feedparser.parse(url)
    return [{"title": e.title, "link": e.link, "published": e.get("published"),
             "source": e.get("source", {}).get("title")} for e in feed.entries]


# 2. Last 24 ghontar fresh news (when:1d / 7d / 1h)
def fresh_news(query):
    return google_news(query, when="1d")


# 3. Specific site theke news (competitor / niche monitoring)
def site_news(site, query=""):
    return google_news(f"{query} site:{site}".strip())


# 4. Google News topic feed (TECHNOLOGY, BUSINESS, SPORTS, HEALTH ...)
def topic_news(topic="TECHNOLOGY", lang="en", country="BD"):
    url = (f"https://news.google.com/rss/headlines/section/topic/{topic}"
           f"?hl={lang}-{country}&gl={country}&ceid={country}:{lang}")
    return [{"title": e.title, "link": e.link} for e in feedparser.parse(url).entries]


# 5. Google Trends: ajker trending search (content idea er gold mine)
def google_trends(geo="BD"):
    feed = feedparser.parse(f"https://trends.google.com/trending/rss?geo={geo}")
    return [{"title": e.title, "traffic": e.get("ht_approx_traffic"),
             "link": e.link} for e in feed.entries]


# 6. Article er full text ber kora (clean, ads chara)
def full_text(url):
    import trafilatura
    html = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True).text
    return trafilatura.extract(html, include_comments=False)


# 7. Duplicate remove (title normalize kore hash)
def dedupe(items):
    seen, out = set(), []
    for it in items:
        key = hashlib.md5(re.sub(r"\W+", "", it["title"].lower()).encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


# 8. Title theke trending keyword / topic idea ber kora
STOP = set("the a an of to in for on and with is at by from as it this that new how why what".split())
def trending_keywords(items, top=20):
    words = [w for it in items for w in re.findall(r"[a-zA-Z]{3,}", it["title"].lower())
             if w not in STOP]
    return Counter(words).most_common(top)


# 9. Onek feed ekshathe fast fetch (parallel)
def fetch_many(urls, workers=8):
    with ThreadPoolExecutor(workers) as ex:
        feeds = list(ex.map(feedparser.parse, urls))
    return [{"title": e.title, "link": e.link, "feed": f.feed.get("title")}
            for f in feeds for e in f.entries]


# 10. Je kono website er hidden RSS feed auto-discover
def discover_rss(site_url):
    soup = BeautifulSoup(requests.get(site_url, headers=HEADERS, timeout=15).text, "html.parser")
    links = soup.find_all("link", type=re.compile(r"(rss|atom)\+xml"))
    return [urljoin(site_url, l.get("href")) for l in links]


# 11. Reddit subreddit RSS (audience er asol prosno / pain point)
def reddit_feed(subreddit, sort="top", t="day"):
    url = f"https://www.reddit.com/r/{subreddit}/{sort}/.rss?t={t}"
    feed = feedparser.parse(url, request_headers=HEADERS)
    return [{"title": e.title, "link": e.link} for e in feed.entries]


# 12. YouTube channel er latest video (competitor tracking)
def youtube_channel(channel_id):
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    return [{"title": e.title, "link": e.link, "published": e.published} for e in feed.entries]


# 13. Page meta data (og:title, og:image, description) - preview card/SEO
def page_meta(url):
    soup = BeautifulSoup(requests.get(url, headers=HEADERS, timeout=15).text, "html.parser")
    g = lambda p: (soup.find("meta", property=p) or {}).get("content")
    return {"title": g("og:title") or (soup.title.string if soup.title else None),
            "image": g("og:image"), "description": g("og:description")}


# 14. Simple extractive summary (frequency based, kono API lagbe na)
def summarize(text, n=3):
    sents = re.split(r"(?<=[.!?])\s+", text)
    freq = Counter(w for w in re.findall(r"\w+", text.lower()) if w not in STOP)
    scored = sorted(sents, key=lambda s: sum(freq[w] for w in re.findall(r"\w+", s.lower())),
                    reverse=True)[:n]
    return " ".join(s for s in sents if s in scored)


# 15. Save + Publish: CSV/JSON export, Telegram channel, WordPress draft
def save(items, name="output"):
    with open(f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    if items:
        with open(f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=items[0].keys())
            w.writeheader(); w.writerows(items)

def publish_telegram(token, chat_id, text):
    return requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         data={"chat_id": chat_id, "text": text}).json()

def publish_wordpress(site, user, app_password, title, content, status="draft"):
    return requests.post(f"{site}/wp-json/wp/v2/posts", auth=(user, app_password),
                         json={"title": title, "content": content, "status": status}).json()


if __name__ == "__main__":
    news = dedupe(fresh_news("artificial intelligence"))
    print("Top news:", [n["title"] for n in news[:5]])
    print("Keywords:", trending_keywords(news, 10))
    print("Trends BD:", [t["title"] for t in google_trends("BD")[:10]])
    save(news, "ai_news")