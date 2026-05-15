"""
agents/self_improvement.py
Agent 10: Analyzes performance, discovers new genres/topics, updates taxonomy.
Runs weekly (performance review) and monthly (genre expansion).
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
import requests
import feedparser
from utils.gemini_client import call_gemini

logger = logging.getLogger(__name__)

TAXONOMY_PATH = Path("taxonomy/taxonomy.json")
CHANGELOG_PATH = Path("taxonomy/taxonomy_changelog.json")
PUBLISHED_POSTS_PATH = Path("logs/published_posts.json")
HEADERS = {"User-Agent": "AutonomousBlogger/1.0"}


class SelfImprovementAgent:
    def __init__(self):
        with open(TAXONOMY_PATH, encoding="utf-8") as f:
            self.taxonomy = json.load(f)
        self.published_posts = self._load_published_posts()

    def _load_published_posts(self) -> list:
        if PUBLISHED_POSTS_PATH.exists():
            with open(PUBLISHED_POSTS_PATH, encoding="utf-8") as f:
                return json.load(f)
        return []

    # ── WEEKLY: Performance Review ────────────────────────────────────────────

    def weekly_review(self) -> dict:
        """Analyze post performance and log insights."""
        if not self.published_posts:
            logger.info("No published posts to review yet.")
            return {}

        # Aggregate by genre and topic
        genre_counts = {}
        topic_counts = {}
        layer_counts = {}

        for post in self.published_posts:
            g = post.get("genre", "unknown")
            t = post.get("topic", "unknown")
            l = post.get("layer", "unknown")
            genre_counts[g] = genre_counts.get(g, 0) + 1
            topic_counts[t] = topic_counts.get(t, 0) + 1
            layer_counts[l] = layer_counts.get(l, 0) + 1

        summary = {
            "review_date": str(datetime.utcnow().date()),
            "total_posts": len(self.published_posts),
            "posts_last_7_days": self._count_recent_posts(7),
            "top_genres": sorted(genre_counts.items(), key=lambda x: -x[1])[:5],
            "top_topics": sorted(topic_counts.items(), key=lambda x: -x[1])[:5],
            "underserved_layers": self._find_underserved_layers(layer_counts),
            "coverage_gaps": self._find_coverage_gaps(),
        }

        logger.info(f"Weekly review: {summary['total_posts']} posts, top genre: {summary['top_genres'][0] if summary['top_genres'] else 'none'}")
        self._log_to_github_summary(summary)
        return summary

    def _count_recent_posts(self, days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = 0
        for post in self.published_posts:
            try:
                pub_date = datetime.fromisoformat(post.get("published_at", "").replace("Z", "+00:00"))
                if pub_date.replace(tzinfo=None) > cutoff:
                    count += 1
            except Exception:
                pass
        return count

    def _find_underserved_layers(self, layer_counts: dict) -> list:
        all_layers = list(self.taxonomy["layers"].keys())
        return [l for l in all_layers if layer_counts.get(l, 0) < 3]

    def _find_coverage_gaps(self) -> list:
        """Find genre/topic combinations with zero posts."""
        published_combos = set(
            f"{p.get('genre','')}/{p.get('topic','')}"
            for p in self.published_posts
        )
        gaps = []
        for genre in self.taxonomy["genres"]:
            for topic in genre["topics"]:
                combo = f"{genre['id']}/{topic['id']}"
                if combo not in published_combos:
                    gaps.append(combo)
        return gaps[:10]

    # ── MONTHLY: Genre Expansion ──────────────────────────────────────────────

    def monthly_expansion(self) -> dict:
        """Scan trends and propose new genres/topics. Auto-update taxonomy."""
        trending = self._fetch_trend_signals()
        existing_genres = [g["id"] for g in self.taxonomy["genres"]]
        existing_topics = {
            g["id"]: [t["id"] for t in g["topics"]]
            for g in self.taxonomy["genres"]
        }

        proposals = self._generate_proposals(trending, existing_genres, existing_topics)

        if proposals.get("new_topics"):
            self._apply_new_topics(proposals["new_topics"])

        if proposals.get("new_genres"):
            self._apply_new_genres(proposals["new_genres"])

        self._save_changelog(proposals)
        logger.info(f"Monthly expansion: {len(proposals.get('new_topics', []))} new topics, {len(proposals.get('new_genres', []))} new genres")
        return proposals

    def _fetch_trend_signals(self) -> list:
        signals = []
        feeds = [
            "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US",
            "https://www.reddit.com/r/futurology/.rss",
            "https://www.reddit.com/r/business/.rss",
        ]
        for feed_url in feeds:
            try:
                resp = requests.get(feed_url, headers=HEADERS, timeout=15)
                feed = feedparser.parse(resp.content)
                signals.extend([e.get("title", "") for e in feed.entries[:15]])
            except Exception as e:
                logger.warning(f"Trend feed failed: {e}")
        return signals[:50]

    def _generate_proposals(self, signals: list, existing_genres: list, existing_topics: dict) -> dict:
        signals_str = "\n".join(f"- {s}" for s in signals)
        genres_str = ", ".join(existing_genres)
        topics_str = json.dumps(existing_topics, indent=2)

        prompt = f"""You are a content strategy director reviewing a blog's taxonomy.

CURRENT TRENDS:
{signals_str}

EXISTING GENRES: {genres_str}
EXISTING TOPICS PER GENRE:
{topics_str}

Your task: Identify 2-3 new TOPICS for existing genres OR 1 new GENRE that:
1. Reflects genuine emerging interest from the trends
2. Is NOT already covered by existing genres/topics
3. Has long-term content potential (not just a momentary spike)
4. Would attract sustainable search traffic

Respond ONLY in JSON:
{{
  "new_topics": [
    {{
      "for_genre": "existing-genre-id",
      "topic_id": "new-topic-slug",
      "topic_label": "Display Name",
      "layers": ["how-to-guides", "explainers", "latest-news"],
      "rationale": "Why this topic matters now"
    }}
  ],
  "new_genres": [
    {{
      "genre_id": "new-genre-slug",
      "genre_label": "Display Name",
      "color": "#hex",
      "description": "One-sentence description",
      "tone_profile": "tone description",
      "starter_topics": [
        {{"id": "topic-slug", "label": "Topic Label", "slug": "topic-slug", "layers": ["explainers", "latest-news"]}}
      ],
      "rationale": "Why this genre is warranted"
    }}
  ],
  "dismissed_signals": ["signal that was too niche or already covered"]
}}"""

        response = call_gemini(prompt, json_mode=True, temperature=0.4)
        try:
            return json.loads(response)
        except Exception:
            return {"new_topics": [], "new_genres": []}

    def _apply_new_topics(self, new_topics: list):
        changed = False
        for new_topic in new_topics:
            for genre in self.taxonomy["genres"]:
                if genre["id"] == new_topic.get("for_genre"):
                    existing_ids = [t["id"] for t in genre["topics"]]
                    if new_topic["topic_id"] not in existing_ids:
                        genre["topics"].append({
                            "id": new_topic["topic_id"],
                            "label": new_topic["topic_label"],
                            "slug": new_topic["topic_id"],
                            "layers": new_topic.get("layers", ["explainers", "latest-news"]),
                        })
                        changed = True
                        logger.info(f"Added topic: {new_topic['topic_id']} to {new_topic['for_genre']}")

        if changed:
            self._save_taxonomy()

    def _apply_new_genres(self, new_genres: list):
        changed = False
        existing_ids = [g["id"] for g in self.taxonomy["genres"]]
        for new_genre in new_genres:
            if new_genre.get("genre_id") not in existing_ids:
                self.taxonomy["genres"].append({
                    "id": new_genre["genre_id"],
                    "label": new_genre["genre_label"],
                    "slug": new_genre["genre_id"],
                    "color": new_genre.get("color", "#6B7280"),
                    "description": new_genre.get("description", ""),
                    "tone_profile": new_genre.get("tone_profile", "informative, balanced"),
                    "topics": new_genre.get("starter_topics", []),
                })
                changed = True
                logger.info(f"Added new genre: {new_genre['genre_id']}")

        if changed:
            self._save_taxonomy()

    def _save_taxonomy(self):
        self.taxonomy["last_updated"] = str(datetime.utcnow().date())
        with open(TAXONOMY_PATH, "w") as f:
            json.dump(self.taxonomy, f, indent=2)
        logger.info("Taxonomy saved.")

    def _save_changelog(self, proposals: dict):
        changelog = []
        if CHANGELOG_PATH.exists():
            with open(CHANGELOG_PATH) as f:
                changelog = json.load(f)
        changelog.append({
            "date": str(datetime.utcnow().date()),
            "type": "monthly_expansion",
            "proposals": proposals,
        })
        with open(CHANGELOG_PATH, "w") as f:
            json.dump(changelog, f, indent=2)

    def _log_to_github_summary(self, summary: dict):
        """Write summary to GitHub Actions step summary."""
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if summary_path:
            with open(summary_path, "a") as f:
                f.write(f"\n## Weekly Blog Performance Review\n")
                f.write(f"- **Total Posts:** {summary['total_posts']}\n")
                f.write(f"- **Last 7 Days:** {summary['posts_last_7_days']}\n")
                f.write(f"- **Top Genres:** {', '.join(g[0] for g in summary['top_genres'][:3])}\n")
                f.write(f"- **Coverage Gaps:** {len(summary['coverage_gaps'])} genre/topic combos\n")
                f.write(f"- **Underserved Layers:** {', '.join(summary['underserved_layers'][:5])}\n")
