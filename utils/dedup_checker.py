"""
dedup_checker.py — Duplicate post detection for the autonomous blogger pipeline.

Prevents publishing posts too similar to existing content by comparing:
1. Exact title match (caught immediately)
2. Normalized title similarity (fuzzy match)
3. URL slug similarity

Uses a simple, dependency-light approach: character n-gram similarity
(no heavy NLP libraries required in the free-tier environment).
"""

import json
import logging
import re
import unicodedata
from pathlib import Path

from config.settings import PipelineConfig

logger = logging.getLogger(__name__)

PUBLISHED_POSTS_LOG = "logs/published_posts.json"

def normalize_text(text: str) -> str:
    """
    Normalize a title for comparison:
    - Lowercase
    - Remove punctuation and special characters
    - Collapse whitespace
    - Remove stop words
    """
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "shall",
        "this", "that", "these", "those", "it", "its", "how", "what",
        "why", "when", "where", "who", "which",
    }

    # Unicode normalization → lowercase
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()

    # Remove non-alphanumeric characters
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Remove stop words
    words = text.split()
    words = [w for w in words if w not in STOP_WORDS and len(w) > 1]

    return " ".join(words)


def ngram_similarity(text1: str, text2: str, n: int = 3) -> float:
    """
    Compute character n-gram based similarity between two normalized texts.
    Returns a score between 0.0 (completely different) and 1.0 (identical).

    Character trigrams are more robust than word-level comparison for
    detecting paraphrased titles and near-duplicates.
    """
    if not text1 or not text2:
        return 0.0

    if text1 == text2:
        return 1.0

    def get_ngrams(text: str, n: int) -> set:
        # Pad text for edge n-grams
        padded = f"{'#' * (n-1)}{text}{'#' * (n-1)}"
        return set(padded[i:i+n] for i in range(len(padded) - n + 1))

    ngrams1 = get_ngrams(text1, n)
    ngrams2 = get_ngrams(text2, n)

    if not ngrams1 or not ngrams2:
        return 0.0

    # Dice coefficient
    intersection = len(ngrams1 & ngrams2)
    return (2.0 * intersection) / (len(ngrams1) + len(ngrams2))


def title_to_slug(title: str) -> str:
    """Convert a post title to a URL slug for comparison."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug

def is_duplicate(topic: str, existing_topics=None) -> bool:
    """
    Return True if `topic` matches or closely resembles any string in existing_topics.
    Used by topic discovery against recent published titles.
    """
    if not topic or not topic.strip() or not existing_topics:
        return False

    t_clean = topic.strip().lower()
    n1 = normalize_text(topic)
    threshold = PipelineConfig.DEDUP_SIMILARITY_THRESHOLD

    for raw in existing_topics:
        if raw is None:
            continue
        s = str(raw).strip()
        if not s:
            continue
        if s.lower() == t_clean:
            return True
        if ngram_similarity(n1, normalize_text(s)) >= threshold:
            return True
    return False


class DedupChecker:
    """Loads published titles/URLs from disk and checks for duplicates (exact + fuzzy)."""

    def __init__(self):
        self._path = Path(PUBLISHED_POSTS_LOG)
        self._posts: list[dict] = []
        self._load()

    def _load(self) -> None:
        self._posts = []
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._posts = data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load published posts log %s: %s", self._path, e)

    def is_duplicate(self, title: str) -> bool:
        if not title or not title.strip():
            return False
        t_clean = title.strip().lower()
        n1 = normalize_text(title)
        threshold = PipelineConfig.DEDUP_SIMILARITY_THRESHOLD
        for post in self._posts:
            prev = (post.get("title") or "").strip()
            if not prev:
                continue
            if prev.lower() == t_clean:
                return True
            if ngram_similarity(n1, normalize_text(prev)) >= threshold:
                return True
        return False

    def add_entry(self, title: str, url: str | None = None) -> None:
        self._posts.append({"title": title, "url": url or ""})
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._posts, f, indent=2)
        except OSError as e:
            logger.warning("Could not persist published posts log: %s", e)
        
class DedupResult:
    """Result object returned by DedupChecker.check()."""

    def __init__(
        self,
        candidate: str,
        is_duplicate: bool,
        similarity_score: float,
        matched_title: str = None,
        matched_url: str = None,
    ):
        self.candidate = candidate
        self.is_duplicate = is_duplicate
        self.similarity_score = similarity_score
        self.matched_title = matched_title
        self.matched_url = matched_url

    def __repr__(self):
        return (
            f"DedupResult(is_duplicate={self.is_duplicate}, "
            f"score={self.similarity_score:.3f}, "
            f"matched='{(self.matched_title or '')[:40]}')"
        )
