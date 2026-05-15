"""
agents/image_agent.py
Agent 7: Finds and embeds images from free sources (Wikimedia, Unsplash, NASA, WHO).
Falls back to Pollinations.ai for AI-generated images.
"""

import logging
import re
import requests
from utils.gemini_client import call_gemini

logger = logging.getLogger(__name__)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "AutonomousBlogger/1.0 (contact@yourblog.com)"}


class ImageAgent:
    def find_images(self, task: dict) -> list:
        """
        Returns list of image dicts: {url, alt, caption, attribution, position}
        """
        genre = task["genre_id"]
        topic = task["topic_label"]
        image_search_query = task["research_brief"].get("suggested_image_search", f"{topic} {genre}")
        title = task["post_draft"]["title"]

        images = []

        # Try Wikimedia Commons first (featured image)
        wm_image = self._search_wikimedia(image_search_query)
        if wm_image:
            wm_image["position"] = "featured"
            images.append(wm_image)
        
        # Try Unsplash for inline image
        unsplash_image = self._get_unsplash(image_search_query)
        if unsplash_image:
            unsplash_image["position"] = "inline-1"
            images.append(unsplash_image)

        # NASA images for science/space content
        if genre in ["science", "environment"] and len(images) < 2:
            nasa_image = self._search_nasa(image_search_query)
            if nasa_image:
                nasa_image["position"] = "inline-2"
                images.append(nasa_image)

        # Fallback to Pollinations.ai
        if not images:
            logger.info("No web images found. Using Pollinations.ai fallback.")
            poll_image = self._get_pollinations_image(title)
            if poll_image:
                poll_image["position"] = "featured"
                images.append(poll_image)

        logger.info(f"Images found: {len(images)}")
        return images[:3]

    def _search_wikimedia(self, query: str) -> dict | None:
        try:
            params = {
                "action": "query",
                "generator": "search",
                "gsrnamespace": "6",  # File namespace
                "gsrsearch": query,
                "gsrlimit": "5",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": "800",
                "format": "json",
            }
            resp = requests.get(WIKIMEDIA_API, params=params, headers=HEADERS, timeout=15)
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            
            for page in pages.values():
                info = page.get("imageinfo", [{}])[0]
                url = info.get("thumburl") or info.get("url", "")
                if not url or not url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    continue
                meta = info.get("extmetadata", {})
                author = meta.get("Artist", {}).get("value", "Wikimedia Commons")
                author = re.sub(r'<[^>]+>', '', author)[:80]
                license_name = meta.get("LicenseShortName", {}).get("value", "CC BY-SA")
                return {
                    "url": url,
                    "alt": f"{query} image",
                    "caption": f"Image related to {query}.",
                    "attribution": f"Credit: {author} via Wikimedia Commons ({license_name})",
                    "source": "wikimedia",
                }
        except Exception as e:
            logger.warning(f"Wikimedia search failed: {e}")
        return None

    def _get_unsplash(self, query: str) -> dict | None:
        try:
            # Unsplash source embed (no API key needed for embed URLs)
            safe_query = re.sub(r'[^a-z0-9\s]', '', query.lower())[:50].strip().replace(' ', ',')
            url = f"https://source.unsplash.com/800x450/?{safe_query}"
            # Verify it resolves
            resp = requests.head(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return {
                    "url": url,
                    "alt": query,
                    "caption": f"Photo via Unsplash.",
                    "attribution": "Photo via <a href='https://unsplash.com'>Unsplash</a>",
                    "source": "unsplash",
                }
        except Exception as e:
            logger.warning(f"Unsplash fetch failed: {e}")
        return None

    def _search_nasa(self, query: str) -> dict | None:
        try:
            resp = requests.get(
                "https://images-api.nasa.gov/search",
                params={"q": query, "media_type": "image", "page_size": 3},
                timeout=15,
            )
            items = resp.json().get("collection", {}).get("items", [])
            for item in items:
                links = item.get("links", [])
                data = item.get("data", [{}])[0]
                for link in links:
                    if link.get("rel") == "preview":
                        return {
                            "url": link["href"],
                            "alt": data.get("title", query),
                            "caption": data.get("description", "")[:120],
                            "attribution": f"Credit: NASA / {data.get('center', '')}",
                            "source": "nasa",
                        }
        except Exception as e:
            logger.warning(f"NASA image search failed: {e}")
        return None

    def _get_pollinations_image(self, prompt: str) -> dict | None:
        try:
            safe_prompt = re.sub(r'[^a-z0-9\s]', '', prompt.lower())[:100].replace(' ', '%20')
            url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=800&height=450&nologo=true"
            return {
                "url": url,
                "alt": prompt,
                "caption": "AI-generated illustration.",
                "attribution": "Image generated via Pollinations.ai",
                "source": "pollinations",
            }
        except Exception as e:
            logger.warning(f"Pollinations fallback failed: {e}")
        return None
