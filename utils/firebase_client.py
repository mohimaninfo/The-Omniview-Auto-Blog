"""
firebase_client.py — Firebase Realtime Database wrapper for post like/reaction counts.

Uses Firebase Admin SDK (server-side) for:
- Initializing per-post like counters when a post is published
- Reading current like counts for reporting
- The actual like/unlike logic runs client-side in the Blogger template JS

Firebase Spark (free) plan limits:
- 1 GB storage
- 10 GB/month download
- 100 simultaneous connections

Data structure in Firebase:
  /likes/{post_id}/
    total: int
    reactions:
      like: int
      insightful: int
      helpful: int
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials
    from firebase_admin import db
except ImportError:  # pragma: no cover - optional dependency
    firebase_admin = None  # type: ignore[assignment]
    credentials = None  # type: ignore[assignment]
    db = None  # type: ignore[assignment]

_firebase_initialized = False
_db = None


def _init_firebase():
    """
    Initialize Firebase Admin SDK using FIREBASE_SERVICE_ACCOUNT_JSON (or
    FIREBASE_CREDENTIALS_JSON) plus FIREBASE_DATABASE_URL from the environment.
    Returns the firebase_admin.db module, or None if unavailable / misconfigured.
    """
    global _firebase_initialized, _db

    if _firebase_initialized:
        return _db

    if firebase_admin is None or credentials is None or db is None:
        logger.warning("firebase-admin not installed; Firebase disabled.")
        return None

    sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "") or os.environ.get(
        "FIREBASE_CREDENTIALS_JSON", ""
    )
    db_url = os.environ.get("FIREBASE_DATABASE_URL", "")

    if not sa_json or not db_url:
        logger.warning("Firebase credentials not set; Firebase disabled.")
        return None

    try:
        info = json.loads(sa_json)
        cred = credentials.Certificate(info)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {"databaseURL": db_url})
        _db = db
        _firebase_initialized = True
        logger.info("Firebase Admin SDK initialized successfully.")
        return _db
    except Exception as e:
        logger.error(f"Firebase initialization failed: {e}")
        return None


class FirebaseClient:
    """
    Manages like/reaction counters in Firebase Realtime Database.
    Designed to be called by Agent 9 (Publisher) when a post goes live.
    """

    def __init__(self):
        self.db = _init_firebase()

    @property
    def available(self) -> bool:
        """Check if Firebase is properly initialized."""
        return self.db is not None

    def initialize_post_counter(self, post_id: str, post_url: str, post_title: str) -> bool:
        """
        Create the initial like counter entry for a newly published post.
        Called by Agent 9 immediately after a post is published.

        Args:
            post_id: Blogger post ID (numeric string)
            post_url: Full URL of the published post
            post_title: Post title for reference

        Returns:
            True if successful, False if Firebase unavailable
        """
        if not self.available:
            logger.warning(f"Firebase unavailable — skipping counter init for post {post_id}")
            return False

        try:
            ref = self.db.reference(f"/likes/{post_id}")

            # Only create if it doesn't already exist
            existing = ref.get()
            if existing:
                logger.debug(f"Like counter already exists for post {post_id}")
                return True

            ref.set({
                "total": 0,
                "post_url": post_url,
                "post_title": post_title[:100],  # Truncate for storage efficiency
                "reactions": {
                    "like": 0,
                    "insightful": 0,
                    "helpful": 0,
                },
                "created_at": {".sv": "timestamp"},  # Firebase server timestamp
            })

            logger.info(f"Like counter initialized for post {post_id}: {post_title[:50]}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize like counter for post {post_id}: {e}")
            return False

    def get_post_likes(self, post_id: str) -> dict:
        """
        Read the current like count for a post.

        Returns:
            Dict with 'total' and 'reactions' keys, or empty dict on failure
        """
        if not self.available:
            return {}

        try:
            ref = self.db.reference(f"/likes/{post_id}")
            data = ref.get()
            return data if data else {"total": 0, "reactions": {}}
        except Exception as e:
            logger.error(f"Failed to get likes for post {post_id}: {e}")
            return {}

    def get_reactions(self, post_id: str) -> dict:
        """Return per-button reaction counts for a post (like / insightful / helpful)."""
        data = self.get_post_likes(post_id)
        nested = data.get("reactions") if isinstance(data.get("reactions"), dict) else {}

        def _count(key: str) -> int:
            if key in nested:
                return int(nested.get(key) or 0)
            v = data.get(key)
            if isinstance(v, (int, float)):
                return int(v)
            return 0

        return {
            "like": _count("like"),
            "insightful": _count("insightful"),
            "helpful": _count("helpful"),
        }

    def increment_reaction(self, post_id: str, reaction: str) -> None:
        """Increment one reaction counter (server-side)."""
        if not self.available:
            return
        try:
            ref = self.db.reference(f"/likes/{post_id}")
            data = ref.get() or {}
            reactions = dict(data.get("reactions") or {})
            reactions[reaction] = int(reactions.get(reaction, 0)) + 1
            payload = {**data, "reactions": reactions}
            payload["total"] = int(data.get("total", 0)) + 1
            ref.set(payload)
        except Exception as e:
            logger.error(f"Failed to increment reaction {reaction} for {post_id}: {e}")

    def get_all_post_likes(self) -> dict:
        """
        Read all post like counts — used by Self-Improvement Agent
        to correlate engagement with content types.

        Returns:
            Dict keyed by post_id
        """
        if not self.available:
            return {}

        try:
            ref = self.db.reference("/likes")
            return ref.get() or {}
        except Exception as e:
            logger.error(f"Failed to fetch all like counts: {e}")
            return {}

    def get_top_posts_by_likes(self, n: int = 10) -> list[dict]:
        """
        Return the top N posts sorted by total likes.
        Used by Self-Improvement Agent for performance analysis.
        """
        all_likes = self.get_all_post_likes()
        if not all_likes:
            return []

        posts = []
        for post_id, data in all_likes.items():
            if isinstance(data, dict):
                posts.append({
                    "post_id": post_id,
                    "total_likes": data.get("total", 0),
                    "post_title": data.get("post_title", ""),
                    "post_url": data.get("post_url", ""),
                    "reactions": data.get("reactions", {}),
                })

        posts.sort(key=lambda x: x["total_likes"], reverse=True)
        return posts[:n]


# ── Client-side Firebase JS for Blogger Template ─────────────────────────────
# This JS snippet is embedded in the Blogger XML template.
# It handles real-time like/reaction interactions in the browser.

FIREBASE_JS_SNIPPET = """
<!-- Firebase Like System -->
<script type="module">
  // Firebase SDK (loaded from CDN — free)
  import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js';
  import { getDatabase, ref, runTransaction, onValue, get }
    from 'https://www.gstatic.com/firebasejs/10.12.0/firebase-database.js';

  const firebaseConfig = {
    databaseURL: "__FIREBASE_DATABASE_URL__",
    // Note: projectId, apiKey etc. needed for client SDK
    // These are PUBLIC client keys — safe to embed
    apiKey: "__FIREBASE_API_KEY__",
    authDomain: "__FIREBASE_AUTH_DOMAIN__",
    projectId: "__FIREBASE_PROJECT_ID__",
    storageBucket: "__FIREBASE_STORAGE_BUCKET__",
    messagingSenderId: "__FIREBASE_MESSAGING_SENDER_ID__",
    appId: "__FIREBASE_APP_ID__"
  };

  const app = initializeApp(firebaseConfig);
  const db = getDatabase(app);

  // Get post ID from the current page's Blogger data
  const postId = document.querySelector('[data-post-id]')?.dataset?.postId;
  if (!postId) return;

  const likesRef = ref(db, `likes/${postId}`);
  const userKey = `liked_${postId}`;

  // ── Read current counts on page load ──────────────────────────────────────
  onValue(likesRef, (snapshot) => {
    const data = snapshot.val() || {};
    const total = data.total || 0;
    const reactions = data.reactions || {};

    // Update total display
    const totalEl = document.getElementById('like-count-total');
    if (totalEl) totalEl.textContent = total;

    // Update individual reaction counts
    ['like', 'insightful', 'helpful'].forEach(type => {
      const el = document.getElementById(`reaction-count-${type}`);
      if (el) el.textContent = reactions[type] || 0;
    });
  });

  // ── Like button click handler ─────────────────────────────────────────────
  window.handleReaction = function(reactionType) {
    const alreadyReacted = localStorage.getItem(`${userKey}_${reactionType}`);

    if (alreadyReacted) {
      // Unlike: remove reaction
      runTransaction(ref(db, `likes/${postId}/total`), (count) => (count || 0) - 1);
      runTransaction(ref(db, `likes/${postId}/reactions/${reactionType}`), (count) => Math.max((count || 0) - 1, 0));
      localStorage.removeItem(`${userKey}_${reactionType}`);
      document.getElementById(`btn-${reactionType}`)?.classList.remove('reacted');
    } else {
      // Like: add reaction
      runTransaction(ref(db, `likes/${postId}/total`), (count) => (count || 0) + 1);
      runTransaction(ref(db, `likes/${postId}/reactions/${reactionType}`), (count) => (count || 0) + 1);
      localStorage.setItem(`${userKey}_${reactionType}`, '1');
      document.getElementById(`btn-${reactionType}`)?.classList.add('reacted');

      // Animate
      const btn = document.getElementById(`btn-${reactionType}`);
      if (btn) {
        btn.classList.add('pop-animation');
        setTimeout(() => btn.classList.remove('pop-animation'), 400);
      }
    }
  };

  // ── Restore reaction states from localStorage on load ────────────────────
  ['like', 'insightful', 'helpful'].forEach(type => {
    if (localStorage.getItem(`${userKey}_${type}`)) {
      document.getElementById(`btn-${type}`)?.classList.add('reacted');
    }
  });
</script>
"""
