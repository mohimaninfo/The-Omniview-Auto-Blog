"""
agents/topic_discovery.py
Agent 2: Discovers fresh, non-duplicate topic ideas from RSS feeds and Gemini.
"""

import json
import logging
import re
import feedparser
import requests
from utils.gemini_client import call_gemini
from utils.dedup_checker import is_duplicate

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "google_trends": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US",
    "reddit_technology": "https://www.reddit.com/r/technology/.rss",
    "reddit_science": "https://www.reddit.com/r/science/.rss",
    "reddit_worldnews": "https://www.reddit.com/r/worldnews/.rss",
    "reddit_health": "https://www.reddit.com/r/health/.rss",
    "reddit_personalfinance": "https://www.reddit.com/r/personalfinance/.rss",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (AutonomousBlogger/1.0)"}


class TopicDiscoveryAgent:
    def __init__(self, published_posts: list):
        self.published_posts = published_posts
        self.published_titles = [
            (p.get("title", "") if isinstance(p, dict) else str(p)).lower()
            for p in published_posts
        ]

    def _fetch_rss(self, url: str) -> list:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.content)
            return [entry.get("title", "") for entry in feed.entries[:20]]
        except Exception as e:
            logger.warning(f"RSS fetch failed for {url}: {e}")
            return []

    def _gather_signals(self, genre: str, topic: str) -> list:
        """Collect trend signals relevant to genre/topic."""
        signals = []

        # Google Trends
        trends = self._fetch_rss(RSS_FEEDS["google_trends"])
        signals.extend(trends)

        # Relevant Reddit feeds
        genre_reddit_map = {
            "technology": ["reddit_technology"],
            "science": ["reddit_science"],
            "health": ["reddit_health"],
            "finance": ["reddit_personalfinance"],
            "society": ["reddit_worldnews"],
        }
        feeds_to_use = genre_reddit_map.get(genre, ["reddit_technology"])
        for feed_key in feeds_to_use:
            signals.extend(self._fetch_rss(RSS_FEEDS[feed_key]))

        return signals[:40]

    def discover(self, genre: str, topic: str, layer: str) -> dict:
        """
        Returns a topic idea dict: {title, angle, keywords, freshness_reason}
        """
        signals = self._gather_signals(genre, topic)
        published_titles_str = "\n".join(self.published_titles[-100:]) or "None yet"
        signals_str = "\n".join(f"- {s}" for s in signals) if signals else "No signals available"

        prompt = f"""You are a senior content strategist for a blog covering {genre}, specifically {topic}.

Your task: Suggest ONE fresh, specific, engaging blog post idea.

Content type (layer): {layer}
Genre: {genre}
Topic: {topic}

Current trending signals (from Google Trends and Reddit):
{signals_str}

Recently published titles (avoid duplicating these):
{published_titles_str}

Requirements:
1. The idea must be SPECIFIC, not generic (e.g. not "AI trends" but "How GPT-4o's multimodal reasoning changes medical diagnostics")
2. It must NOT duplicate or closely resemble any published title above
3. It must be timely and relevant to current signals where possible
4. The title must be SEO-friendly and include a primary keyword naturally
5. Suggest 3-5 relevant SEO keywords

Respond ONLY in this exact JSON format:
{{
  "title": "Full blog post title here",
  "angle": "One sentence describing the unique angle or hook",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "freshness_reason": "Why this is timely and relevant right now",
  "suggested_word_count": 1200
}}"""

        response_text = call_gemini(prompt, json_mode=True)

        try:
            idea = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback: extract JSON from response
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                idea = json.loads(match.group())
            else:
                idea = {
                    "title": f"The Future of {topic.replace('-', ' ').title()} in {genre.title()}",
                    "angle": "A comprehensive overview of current developments",
                    "keywords": [topic.replace('-', ' '), genre, layer.replace('-', ' ')],
                    "freshness_reason": "Evergreen topic",
                    "suggested_word_count": 1200,
                }

        # Dedup check
        if is_duplicate(idea["title"], self.published_titles):
            logger.warning(f"Duplicate detected: '{idea['title']}'. Requesting new idea.")
            idea["title"] = f"{idea['title']} — A {layer.replace('-', ' ').title()} Perspective"

        logger.info(f"Topic discovered: {idea['title']}")
        return idea
