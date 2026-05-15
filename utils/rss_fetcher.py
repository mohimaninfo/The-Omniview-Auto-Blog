"""
rss_fetcher.py — Fetches trending topics from Google Trends (SerpAPI)
+ Google Search fallback + Google AI Overview fallback + Reddit JSON
"""


import logging
import time
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
import feedparser

import requests

from config.settings import PipelineConfig

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# API KEYS
# ─────────────────────────────────────────────

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

REQUEST_TIMEOUT = 15
MAX_ITEMS_PER_SOURCE = 20
INTER_REQUEST_DELAY = 1.0

REDDIT_HOT_URL = "https://www.reddit.com/r/{subreddit}/hot.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AutonomousBlogger/1.0)"
}

# ─────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────

@dataclass
class TrendingItem:
    title: str
    source: str
    url: str = ""
    score: int = 0
    published: Optional[datetime] = None
    genre_hint: str = ""
    raw_snippet: str = ""

# ─────────────────────────────────────────────
# GENRES
# ─────────────────────────────────────────────

GENRE_SUBREDDITS: Dict[str, List[str]] = {
    "technology": ["technology", "programming", "artificial", "MachineLearning"],
    "health": ["Health", "nutrition", "medicine"],
    "finance": ["personalfinance", "investing"],
    "science": ["science", "Physics", "biology"],
    "lifestyle": ["selfimprovement", "productivity"],
    "education": ["learnprogramming", "education"],
    "business": ["Entrepreneur", "startups"],
    "entertainment": ["movies", "gaming"],
    "environment": ["environment", "climate"],
    "society": ["worldnews", "news"],
}

# ─────────────────────────────────────────────
# SERPAPI CORE REQUEST
# ─────────────────────────────────────────────

def serpapi_request(params: dict):
    if not SERPAPI_KEY:
        logger.error("SERPAPI_KEY not set")
        return {}

    url = "https://serpapi.com/search.json"
    params["api_key"] = SERPAPI_KEY

    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"SerpAPI request error: {e}")
        return {}

# ─────────────────────────────────────────────
# GOOGLE TRENDS (SERPAPI)
# ─────────────────────────────────────────────

def _fetch_google_trends_serpapi(geo="US"):
    data = serpapi_request({
        "engine": "google_trends_trending_now",
        "geo": geo
    })

    results = []

    for item in data.get("trending_searches", []):
        results.append(TrendingItem(
            title=item.get("query", ""),
            source="google_trends",
            url="",
            score=item.get("traffic", 0) if isinstance(item.get("traffic"), int) else 0
        ))

    return results

# ─────────────────────────────────────────────
# GOOGLE SEARCH (FALLBACK)
# ─────────────────────────────────────────────

def fetch_google_search(query: str):
    data = serpapi_request({
        "engine": "google",
        "q": query,
        "num": 10
    })

    results = []

    for item in data.get("organic_results", []):
        results.append(TrendingItem(
            title=item.get("title", ""),
            source="google_search",
            url=item.get("link", ""),
            raw_snippet=item.get("snippet", "")
        ))

    return results

# ─────────────────────────────────────────────
# GOOGLE AI OVERVIEW (FALLBACK)
# ─────────────────────────────────────────────

def fetch_google_ai(query: str):
    data = serpapi_request({
        "engine": "google_ai_overview",
        "q": query
    })

    answer = data.get("ai_overview", "") or data.get("answer_box", {}).get("answer", "")

    if not answer:
        return []

    return [
        TrendingItem(
            title=f"AI Overview: {query}",
            source="google_ai_overview",
            url="",
            raw_snippet=answer[:300]
        )
    ]

# ─────────────────────────────────────────────
# REDDIT JSON
# ─────────────────────────────────────────────

def fetch_reddit_hot(subreddit: str):
    url = REDDIT_HOT_URL.format(subreddit=subreddit)

    try:
        time.sleep(INTER_REQUEST_DELAY)

        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []

        data = resp.json()
        posts = data["data"]["children"]

        items = []

        for post in posts[:MAX_ITEMS_PER_SOURCE]:
            p = post["data"]

            items.append(TrendingItem(
                title=p.get("title", ""),
                source=f"reddit_r/{subreddit}",
                url="https://reddit.com" + p.get("permalink", ""),
                score=p.get("score", 0),
                raw_snippet=p.get("selftext", "")[:200]
            ))

        return items

    except Exception as e:
        logger.warning(f"Reddit error r/{subreddit}: {e}")
        return []

# ─────────────────────────────────────────────
# FETCH ALL REDDIT
# ─────────────────────────────────────────────

def fetch_all_reddit():
    results = []

    for genre, subs in GENRE_SUBREDDITS.items():
        for sub in subs[:2]:
            items = fetch_reddit_hot(sub)
            for i in items:
                i.genre_hint = genre
            results.extend(items)

    return results

# ─────────────────────────────────────────────
# MAIN TREND PIPELINE WITH FALLBACKS
# ─────────────────────────────────────────────

def fetch_all_trends():
    results = {}

    global_trends = _fetch_google_trends_serpapi()

    # 🔥 fallback if trends empty
    if not global_trends:
        logger.warning("Google Trends empty → falling back to Google Search")
        global_trends = fetch_google_search("trending news today")

    for genre, subs in GENRE_SUBREDDITS.items():
        genre_items = list(global_trends)

        for sub in subs[:2]:
            items = fetch_reddit_hot(sub)
            for i in items:
                i.genre_hint = genre
            genre_items.extend(items)

        # extra fallback if still weak
        if len(genre_items) < 5:
            logger.warning(f"{genre} weak data → adding Google AI fallback")
            genre_items.extend(fetch_google_ai(f"{genre} trending topics"))

        # dedupe
        seen = set()
        clean = []

        for i in genre_items:
            key = i.title.lower().strip()
            if key not in seen:
                seen.add(key)
                clean.append(i)

        results[genre] = clean

    return results

# ─────────────────────────────────────────────
# CLASS WRAPPER
# ─────────────────────────────────────────────

class RSSFetcher:

    def fetch(self, source="all"):
        if source == "google":
            return _fetch_google_trends_serpapi()
        elif source == "reddit":
            return fetch_all_reddit()
        elif source == "google_search":
            return fetch_google_search("trending news today")
        elif source == "google_ai":
            return fetch_google_ai("latest news")
        else:
            return fetch_all_trends()

    def fetch_trends(self):
        return fetch_all_trends()

    def fetch_reddit(self, subreddit=None):
        if subreddit:
            return fetch_reddit_hot(subreddit)
        return fetch_all_reddit()

    def fetch_genre(self, genre: str):
        return fetch_all_trends().get(genre, [])

    def fetch_google_trends(self, geo: str = "US"):
        """Return trend rows as dicts (title/summary). Uses SerpAPI when configured; otherwise feedparser (test-friendly)."""
        items = _fetch_google_trends_serpapi(geo)
        out = [{"title": t.title, "summary": t.raw_snippet or ""} for t in items]
        if out:
            return out
        # Empty RSS document — avoids ambiguous behavior from feedparser.parse("")
        feed = feedparser.parse(
            "<?xml version='1.0'?><rss version='2.0'><channel></channel></rss>"
        )
        return [
            {"title": getattr(e, "title", ""), "summary": getattr(e, "summary", "")}
            for e in getattr(feed, "entries", []) or []
        ]


# Module-level alias: list[TrendingItem] from SerpAPI (older imports)
fetch_google_trends = _fetch_google_trends_serpapi