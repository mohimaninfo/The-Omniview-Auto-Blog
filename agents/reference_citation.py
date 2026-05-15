"""
agents/reference_citation.py
Agent 5: Validates and formats the reference list; inserts citation markers into HTML.
"""

import json
import logging
import re
from datetime import date
from utils.gemini_client import call_gemini
from utils.link_validator import validate_url_with_fallback

logger = logging.getLogger(__name__)


class ReferenceCitationAgent:
    def process(self, task: dict) -> dict:
        """
        Inserts superscript citation markers and appends a formatted reference section.
        Returns dict with updated html_body and references list.
        """
        research_brief = task["research_brief"]
        post_draft = task["post_draft"]
        html_body = post_draft["html_body"]

        # Build reference list from source URLs in research brief
        raw_sources = research_brief.get("source_urls", [])
        key_facts = research_brief.get("key_facts", [])
        expert_quotes = research_brief.get("expert_quotes", [])
        statistics = research_brief.get("statistics", [])

        # Collect all source URLs with metadata
        all_sources = {}
        counter = 1

        for item in key_facts + statistics:
            url = item.get("source_url", "")
            if url and url not in all_sources:
                validated_url = validate_url_with_fallback(url)
                all_sources[url] = {
                    "index": counter,
                    "source_name": item.get("source_name", "Source"),
                    "url": validated_url,
                    "year": item.get("year", date.today().year),
                    "accessed": str(date.today()),
                }
                counter += 1

        for item in expert_quotes:
            url = item.get("source_url", "")
            if url and url not in all_sources:
                validated_url = validate_url_with_fallback(url)
                all_sources[url] = {
                    "index": counter,
                    "source_name": f"{item.get('expert_name', 'Expert')}, {item.get('expert_title', '')}",
                    "url": validated_url,
                    "year": date.today().year,
                    "accessed": str(date.today()),
                }
                counter += 1

        # Add any remaining raw_sources not yet included
        for url in raw_sources:
            if url and url not in all_sources:
                validated_url = validate_url_with_fallback(url)
                all_sources[url] = {
                    "index": counter,
                    "source_name": url.split('/')[2] if '/' in url else url,
                    "url": validated_url,
                    "year": date.today().year,
                    "accessed": str(date.today()),
                }
                counter += 1

        references = sorted(all_sources.values(), key=lambda x: x["index"])

        # Build HTML reference section
        ref_html = self._build_reference_html(references)

        # Ask Gemini to insert citation markers into the existing HTML
        if references:
            html_body = self._insert_citations(html_body, research_brief, references)

        full_html = html_body + "\n" + ref_html

        return {
            "html_body": full_html,
            "references": references,
        }

    def _insert_citations(self, html: str, brief: dict, references: list) -> str:
        """Uses Gemini to insert ¹²³ citation markers after factual claims."""
        ref_summary = "\n".join(
            f"[{r['index']}] {r['source_name']} — {r['url']}"
            for r in references[:10]
        )

        prompt = f"""You are a copy editor. Add superscript citation markers to the HTML below.

REFERENCES AVAILABLE:
{ref_summary}

INSTRUCTIONS:
1. After each factual claim, statistic, or direct/paraphrased expert statement, add a superscript: <sup>[1]</sup>
2. Match claims to the most relevant reference number based on source name
3. Do NOT add citations where none are appropriate
4. Do NOT change the HTML structure, just insert <sup> tags
5. Return the complete HTML with citations inserted

HTML TO ANNOTATE:
{html[:6000]}

Return only the annotated HTML:"""

        try:
            annotated = call_gemini(prompt, max_tokens=8192, temperature=0.1)
            # Strip any markdown code fences
            annotated = re.sub(r'^```html?\n?|```$', '', annotated.strip())
            return annotated
        except Exception as e:
            logger.warning(f"Citation insertion failed: {e}. Returning original HTML.")
            return html

    def _build_reference_html(self, references: list) -> str:
        if not references:
            return ""

        items = ""
        for ref in references:
            items += f"""
    <li id="ref-{ref['index']}">
      [{ref['index']}] {ref['source_name']}.
      <a href="{ref['url']}" target="_blank" rel="noopener noreferrer nofollow">{ref['url']}</a>.
      Accessed {ref['accessed']}.
    </li>"""

        return f"""
<section class="references-section" aria-label="References">
  <h2>References</h2>
  <ol class="reference-list">
{items}
  </ol>
</section>"""
