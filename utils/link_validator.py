"""
link_validator.py — Validates reference URLs and falls back to archive.org.

Used by Agent 5 (Reference & Citation Agent) to ensure every cited URL
is reachable. Dead links are replaced with their archived version if available.

Strategy:
1. HTTP HEAD request (fast, minimal bandwidth)
2. If 4xx/5xx or timeout → query Wayback Machine CDX API for latest snapshot
3. If snapshot found → replace URL with archive.org link
4. If no snapshot → flag as UNVERIFIED and mark for removal
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def _validated_link_to_legacy_dict(link: "ValidatedLink") -> dict:
    """Shape expected by older tests: valid flag, url, optional archive_url."""
    return {
        "valid": link.status == LinkStatus.LIVE,
        "url": link.original_url,
        "archive_url": link.final_url if link.status == LinkStatus.ARCHIVED else None,
    }


class LinkValidator:
    def __init__(self):
        pass

    def validate(self, url: str) -> dict:
        return _validated_link_to_legacy_dict(validate_url(url))

    def validate_batch(self, urls: list) -> list[dict]:
        return [_validated_link_to_legacy_dict(validate_url(u)) for u in urls]


def validate_url_with_fallback(url: str) -> str:
    """
    Validate URL accessibility.
    Returns original URL if valid, otherwise '#'.
    """

    if not url:
        return "#"

    try:
        response = requests.head(
            url,
            allow_redirects=True,
            timeout=5
        )

        if response.status_code < 400:
            return url

        logger.warning(f"Invalid URL: {url} ({response.status_code})")

    except Exception as e:
        logger.warning(f"URL validation failed: {url} — {e}")

    return "#"


def validate_urls(urls: list) -> list:
    """
    Validate multiple URLs.
    Returns only valid URLs.
    """

    valid = []

    for url in urls:
        checked = validate_url_with_fallback(url)

        if checked != "#":
            valid.append(checked)

    return valid


class LinkStatus(str, Enum):
    LIVE = "live"
    ARCHIVED = "archived"
    DEAD = "dead"
    SKIPPED = "skipped"       # Non-HTTP URLs, localhost, etc.
    RATE_LIMITED = "rate_limited"


@dataclass
class ValidatedLink:
    original_url: str
    final_url: str
    status: LinkStatus
    http_status_code: Optional[int] = None
    archive_timestamp: Optional[str] = None
    error: Optional[str] = None


# ── Constants ─────────────────────────────────────────────────────────────────
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE_URL = "https://web.archive.org/web"

# Domains that regularly block HEAD requests — treat as live by assumption
TRUSTED_DOMAINS = {
    "doi.org", "pubmed.ncbi.nlm.nih.gov", "scholar.google.com",
    "nature.com", "science.org", "thelancet.com", "nejm.org",
    "who.int", "cdc.gov", "nih.gov", "gov.uk", "europa.eu",
    "wikipedia.org", "commons.wikimedia.org",
}

REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 2
RETRY_DELAY = 1.0     # seconds between retries

# Rate limit for validation calls (to avoid hammering external servers)
INTER_REQUEST_DELAY = 0.5  # seconds between requests


def _is_valid_url(url: str) -> bool:
    """Check if a URL is a proper HTTP/HTTPS URL worth validating."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _domain_of(url: str) -> str:
    """Extract the base domain from a URL."""
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _head_request(url: str) -> tuple[Optional[int], Optional[str]]:
    """
    Perform an HTTP HEAD request.
    Returns (status_code, error_message).
    Falls back to GET if server doesn't support HEAD.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AutonomousBlogger/1.0; "
            "+https://github.com/your-username/autonomous-blogger)"
        )
    }

    for attempt in range(MAX_RETRIES):
        try:
            # Try HEAD first (lightweight)
            resp = requests.head(
                url, headers=headers, timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )
            if resp.status_code == 405:
                # HEAD not allowed — fallback to GET with stream
                resp = requests.get(
                    url, headers=headers, timeout=REQUEST_TIMEOUT,
                    allow_redirects=True, stream=True
                )
                resp.close()
            return resp.status_code, None

        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES - 1:
                return None, "Timeout"
            time.sleep(RETRY_DELAY)

        except requests.exceptions.TooManyRedirects:
            return None, "TooManyRedirects"

        except requests.exceptions.ConnectionError as e:
            if attempt == MAX_RETRIES - 1:
                return None, f"ConnectionError: {str(e)[:80]}"
            time.sleep(RETRY_DELAY)

        except Exception as e:
            return None, str(e)[:80]

    return None, "MaxRetriesExceeded"


def _get_archive_url(url: str) -> Optional[str]:
    """
    Query the Wayback Machine CDX API for the most recent snapshot of a URL.
    Returns the archive URL string, or None if no snapshot found.

    CDX API docs: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
    """
    try:
        params = {
            "url": url,
            "output": "json",
            "limit": 1,
            "fl": "timestamp,statuscode",
            "filter": "statuscode:200",
            "collapse": "timestamp:8",  # Group by day
        }
        resp = requests.get(
            WAYBACK_CDX_URL, params=params,
            timeout=REQUEST_TIMEOUT
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        # data[0] is the header row, data[1] is the first result
        if len(data) < 2:
            return None

        row = data[1]  # [timestamp, statuscode]
        timestamp = row[0]
        status = row[1]

        if status == "200":
            archive_url = f"{WAYBACK_BASE_URL}/{timestamp}/{url}"
            return archive_url

        return None

    except Exception as e:
        logger.debug(f"Wayback CDX lookup failed for {url}: {e}")
        return None


def validate_url(url: str) -> ValidatedLink:
    """
    Validate a single URL and return a ValidatedLink result.

    Logic:
    1. Check if URL is well-formed
    2. If from a trusted domain → assume live (skip HEAD)
    3. HEAD request to check liveness
    4. If dead → try Wayback Machine
    5. Return final status and URL to use
    """
    if not url or not isinstance(url, str):
        return ValidatedLink(
            original_url=str(url),
            final_url=str(url),
            status=LinkStatus.SKIPPED,
            error="Empty or non-string URL"
        )

    url = url.strip()

    if not _is_valid_url(url):
        return ValidatedLink(
            original_url=url,
            final_url=url,
            status=LinkStatus.SKIPPED,
            error="Not a valid HTTP/HTTPS URL"
        )

    # Trusted domains — skip HEAD to avoid false negatives from bot blockers
    domain = _domain_of(url)
    if any(url.endswith(td) or domain == td or domain.endswith("." + td)
           for td in TRUSTED_DOMAINS):
        logger.debug(f"Trusted domain — assuming live: {url}")
        return ValidatedLink(
            original_url=url,
            final_url=url,
            status=LinkStatus.LIVE,
            http_status_code=200
        )

    # Rate limit between requests
    time.sleep(INTER_REQUEST_DELAY)

    # HEAD request
    status_code, error = _head_request(url)

    if status_code and 200 <= status_code < 400:
        return ValidatedLink(
            original_url=url,
            final_url=url,
            status=LinkStatus.LIVE,
            http_status_code=status_code
        )

    # URL appears dead — try Wayback Machine
    logger.debug(f"URL appears dead (status={status_code}, error={error}): {url}")
    logger.debug(f"Querying Wayback Machine for: {url}")

    time.sleep(INTER_REQUEST_DELAY)
    archive_url = _get_archive_url(url)

    if archive_url:
        logger.info(f"URL replaced with archive: {url} → {archive_url}")
        return ValidatedLink(
            original_url=url,
            final_url=archive_url,
            status=LinkStatus.ARCHIVED,
            http_status_code=status_code,
            error=error
        )

    logger.warning(f"URL dead and no archive found: {url}")
    return ValidatedLink(
        original_url=url,
        final_url=url,
        status=LinkStatus.DEAD,
        http_status_code=status_code,
        error=error or "No archive snapshot available"
    )


def validate_urls_batch(urls: list[str]) -> list[ValidatedLink]:
    """
    Validate a list of URLs, returning results in the same order.
    Logs a summary of live/archived/dead counts.
    """
    results = []

    for i, url in enumerate(urls):
        logger.debug(f"Validating URL {i+1}/{len(urls)}: {url[:80]}")
        result = validate_url(url)
        results.append(result)

    # Summary log
    live = sum(1 for r in results if r.status == LinkStatus.LIVE)
    archived = sum(1 for r in results if r.status == LinkStatus.ARCHIVED)
    dead = sum(1 for r in results if r.status == LinkStatus.DEAD)
    skipped = sum(1 for r in results if r.status == LinkStatus.SKIPPED)

    logger.info(
        f"URL validation summary: "
        f"{live} live | {archived} archived | {dead} dead | {skipped} skipped"
        f" (of {len(urls)} total)"
    )

    return results


def filter_valid_references(references: list[dict]) -> list[dict]:
    """
    Given a list of reference dicts with a 'url' key, validate all URLs
    and return the filtered list with:
    - Dead references removed
    - Archived references updated with the archive URL
    - Live references kept as-is

    Each reference dict should have at minimum: {'url': str, 'title': str, ...}
    """
    urls = [ref.get("url", "") for ref in references]
    results = validate_urls_batch(urls)

    valid_refs = []
    for ref, result in zip(references, results):
        if result.status == LinkStatus.DEAD:
            logger.warning(f"Removing dead reference: {ref.get('title', ref.get('url', '?'))}")
            continue  # Drop dead links

        updated_ref = dict(ref)
        updated_ref["url"] = result.final_url

        if result.status == LinkStatus.ARCHIVED:
            updated_ref["note"] = "[Archived version via Wayback Machine]"

        valid_refs.append(updated_ref)

    logger.info(
        f"References: {len(references)} in → {len(valid_refs)} valid "
        f"({len(references) - len(valid_refs)} removed)"
    )
    return valid_refs
