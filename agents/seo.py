"""
agents/seo.py
Agent 6: SEO — Generates JSON-LD schema, Open Graph tags, labels, and meta data.
"""

import json
import logging
import math
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

SCHEMA_TYPES = {
    "latest-news": "NewsArticle",
    "research-articles": "ScholarlyArticle",
    "how-to-guides": "HowTo",
    "opinion-analysis": "OpinionNewsArticle",
    "case-studies": "Article",
    "interviews": "Article",
    "listicles": "ItemList",
    "reviews": "Review",
    "explainers": "Article",
}

AUTHOR_BYLINES = {
    "technology": "Alex Chen, Technology Correspondent",
    "health": "Dr. Maya Patel, Health & Wellness Editor",
    "finance": "Marcus Webb, Financial Analyst",
    "science": "Dr. Sarah Okonkwo, Science Journalist",
    "lifestyle": "Jordan Taylor, Lifestyle Editor",
    "business": "Daniel Park, Business Reporter",
    "education": "Emma Rossi, Education Writer",
    "environment": "Liam Torres, Environmental Correspondent",
    "society": "Aisha Williams, Society & Culture Editor",
    "entertainment": "Riley Johnson, Entertainment Editor",
}


class SEOAgent:
    def optimize(self, task: dict) -> dict:
        genre_id = task["genre_id"]
        genre_slug = task["genre_slug"]
        topic_slug = task["topic_slug"]
        layer_slug = task["layer_meta"]["slug"]
        slug = task["post_draft"]["slug"]
        title = task["post_draft"]["title"]
        meta_description = task["post_draft"]["meta_description"]
        keywords = task["topic_idea"]["keywords"]
        layer = task["layer"]
        genre_label = task["genre_label"]
        topic_label = task["topic_label"]
        layer_label = task["layer_meta"]["label"]
        genre_color = task["genre_color"]

        author = AUTHOR_BYLINES.get(genre_id, "Editorial Team")
        schema_type = SCHEMA_TYPES.get(layer, "Article")
        pub_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        blog_base = os.environ.get("BLOG_PUBLIC_BASE_URL", "https://yourblog.blogspot.com").rstrip("/")
        canonical_url = f"{blog_base}/{genre_slug}/{topic_slug}/{layer_slug}/{slug}"

        # Blogger labels: genre + topic + layer + keywords
        labels = [genre_label, topic_label, layer_label] + keywords[:3]

        # JSON-LD Schema
        json_ld = {
            "@context": "https://schema.org",
            "@type": schema_type,
            "headline": title,
            "description": meta_description,
            "author": {"@type": "Person", "name": author},
            "publisher": {
                "@type": "Organization",
                "name": "YourBlog",
                "url": blog_base,
            },
            "datePublished": pub_date,
            "dateModified": pub_date,
            "url": canonical_url,
            "keywords": ", ".join(keywords),
            "articleSection": genre_label,
            "inLanguage": "en-US",
        }

        schema_script = f'<script type="application/ld+json">\n{json.dumps(json_ld, indent=2)}\n</script>'

        # Open Graph + Twitter Card meta tags
        og_tags = f"""<!-- Open Graph -->
<meta property="og:title" content="{self._escape(title)}" />
<meta property="og:description" content="{self._escape(meta_description)}" />
<meta property="og:type" content="article" />
<meta property="og:url" content="{canonical_url}" />
<meta property="og:site_name" content="YourBlog" />
<meta property="article:section" content="{genre_label}" />
<meta property="article:tag" content="{', '.join(keywords)}" />
<meta property="article:published_time" content="{pub_date}" />

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{self._escape(title)}" />
<meta name="twitter:description" content="{self._escape(meta_description)}" />

<!-- Canonical -->
<link rel="canonical" href="{canonical_url}" />

<!-- Meta -->
<meta name="description" content="{self._escape(meta_description)}" />
<meta name="keywords" content="{', '.join(keywords)}" />"""

        # Read time estimate
        word_count = task["post_draft"].get("estimated_word_count", 1200)
        read_time = max(1, math.ceil(word_count / 238))

        return {
            "canonical_url": canonical_url,
            "labels": labels,
            "author": author,
            "schema_script": schema_script,
            "og_tags": og_tags,
            "read_time_minutes": read_time,
            "pub_date": pub_date,
            "slug": slug,
        }

    def _escape(self, text: str) -> str:
        return text.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
