"""
agents/video_agent.py
Agent 8: Video — Decides if a video is necessary, then fetches from YouTube.
[J] Video necessity decision prompt included here.
"""

import logging
import json
import re
import os
import requests
from utils.gemini_client import call_gemini

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class VideoAgent:
    def decide_and_fetch(self, task: dict) -> dict:
        """
        [J] Returns dict: {needed: bool, reason: str, embed_html: str | None}
        """
        layer = task["layer"]
        genre = task["genre_label"]
        topic = task["topic_label"]
        title = task["post_draft"]["title"]
        video_search_query = task["research_brief"].get("suggested_video_search", title)

        # [J] Video necessity decision prompt
        decision_prompt = f"""You are a content editor deciding whether a YouTube video embed is necessary for a blog post.

POST DETAILS:
- Title: {title}
- Genre: {genre}
- Topic: {topic}
- Content Layer: {layer}

DECISION RULES (apply strictly):
- "how-to-guides": Video IS needed if the process involves physical actions, UI navigation, or complex sequences
- "latest-news": Video is RARELY needed unless it's a video-first story (e.g., press conference)
- "explainers": Video is helpful if the concept is visual or mechanical
- "research-articles": Video is NOT needed; academic readers prefer text
- "opinion-analysis": Video is NOT needed
- "listicles": Video is NOT needed
- "reviews": Video is helpful for product demos only
- "interviews": Video is helpful if it is a filmed interview
- "case-studies": Video is helpful if it includes a demo or walkthrough

RESPOND in JSON only:
{{
  "needed": true or false,
  "reason": "One sentence explaining the decision",
  "search_query": "YouTube search query to find the best video (only if needed=true)"
}}"""

        response_text = call_gemini(decision_prompt, json_mode=True, temperature=0.1)

        try:
            decision = json.loads(response_text)
        except Exception:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            decision = json.loads(match.group()) if match else {"needed": False, "reason": "Parse error"}

        logger.info(f"Video decision: needed={decision.get('needed')} — {decision.get('reason')}")

        result = {
            "needed": decision.get("needed", False),
            "reason": decision.get("reason", ""),
            "embed_html": None,
            "video_id": None,
            "video_title": None,
        }

        if decision.get("needed") and YOUTUBE_API_KEY:
            search_query = decision.get("search_query", video_search_query)
            video_data = self._fetch_youtube_video(search_query)
            if video_data:
                result.update(video_data)
                result["embed_html"] = self._build_embed(video_data["video_id"], video_data["video_title"])

        return result

    def _fetch_youtube_video(self, query: str) -> dict | None:
        try:
            resp = requests.get(YOUTUBE_SEARCH_URL, params={
                "key": YOUTUBE_API_KEY,
                "q": query,
                "type": "video",
                "part": "id,snippet",
                "maxResults": 5,
                "order": "relevance",
                "videoDuration": "medium",
                "videoEmbeddable": "true",
                "safeSearch": "strict",
            }, timeout=15)
            items = resp.json().get("items", [])
            if items:
                item = items[0]
                return {
                    "video_id": item["id"]["videoId"],
                    "video_title": item["snippet"]["title"],
                    "channel": item["snippet"]["channelTitle"],
                }
        except Exception as e:
            logger.warning(f"YouTube search failed: {e}")
        return None

    def _build_embed(self, video_id: str, title: str) -> str:
        return f"""<div class="video-embed-wrapper" style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;">
  <iframe
    src="https://www.youtube.com/embed/{video_id}?rel=0&modestbranding=1"
    title="{title}"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen
    style="position:absolute;top:0;left:0;width:100%;height:100%;"
    loading="lazy">
  </iframe>
</div>
<p class="video-caption"><em>Video: {title}</em></p>"""
