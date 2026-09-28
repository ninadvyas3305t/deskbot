"""Modular web search capability for DeskBot."""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WebSearchProvider(ABC):
    """Abstract interface for web search providers."""

    @abstractmethod
    def search(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        """Execute a web search and return structured results."""
        pass


def _get_ssl_context():
    """Create a resilient SSL context, falling back to unverified if local certificates fail."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl._create_unverified_context()
    except Exception:
        return ssl.create_default_context()


class DuckDuckGoSearchProvider(WebSearchProvider):
    """Zero-dependency DuckDuckGo search provider using standard web endpoints."""

    BASE_URL = "https://html.duckduckgo.com/html/"
    API_URL = "https://api.duckduckgo.com/"

    def search(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        import ssl
        clean_query = query.strip()
        if not clean_query:
            return []

        results: List[Dict[str, str]] = []
        ssl_ctx = _get_ssl_context()

        # 1. Try DuckDuckGo Instant Answer API first
        try:
            api_params = urllib.parse.urlencode({"q": clean_query, "format": "json", "no_html": "1"})
            api_req = urllib.request.Request(
                f"{self.API_URL}?{api_params}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            try:
                resp_ctx = urllib.request.urlopen(api_req, context=ssl_ctx, timeout=4.0)
            except ssl.SSLError:
                resp_ctx = urllib.request.urlopen(api_req, context=ssl._create_unverified_context(), timeout=4.0)
            
            with resp_ctx as resp:
                import json
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                abstract = data.get("AbstractText", "").strip()
                heading = data.get("Heading", "").strip()
                source_url = data.get("AbstractURL", "").strip()
                if abstract:
                    results.append({
                        "title": heading or clean_query,
                        "snippet": abstract,
                        "url": source_url or "https://duckduckgo.com",
                    })
        except Exception as api_err:
            logger.debug("DuckDuckGo Instant Answer API note: %s", api_err)

        if len(results) >= max_results:
            return results[:max_results]

        # 2. Scrape HTML results if instant answer didn't satisfy
        try:
            data_bytes = urllib.parse.urlencode({"q": clean_query}).encode("utf-8")
            req = urllib.request.Request(
                self.BASE_URL,
                data=data_bytes,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            try:
                resp_ctx = urllib.request.urlopen(req, context=ssl_ctx, timeout=5.0)
            except ssl.SSLError:
                resp_ctx = urllib.request.urlopen(req, context=ssl._create_unverified_context(), timeout=5.0)
            
            with resp_ctx as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")

            # Extract real titles and links from class="result__a" and snippets from class="result__snippet"
            titles_raw = re.findall(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', raw_html)
            urls_raw = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', raw_html)
            snippet_matches = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', raw_html)

            for i in range(min(len(snippet_matches), max_results - len(results))):
                title_clean = re.sub(r"<[^>]+>", "", titles_raw[i]) if i < len(titles_raw) else f"Result {len(results) + 1}"
                title_clean = html.unescape(title_clean).strip()
                snippet_clean = re.sub(r"<[^>]+>", "", snippet_matches[i])
                snippet_clean = html.unescape(snippet_clean).strip()
                url = urls_raw[i] if i < len(urls_raw) else "https://duckduckgo.com"
                if "uddg=" in url:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                    url = parsed.get("uddg", [url])[0]

                if snippet_clean:
                    results.append({
                        "title": title_clean or f"Result {len(results) + 1}",
                        "snippet": snippet_clean,
                        "url": url,
                    })
        except Exception as scrape_err:
            logger.debug("DuckDuckGo HTML query fallback error: %s", scrape_err)

        return results[:max_results]


_DEFAULT_PROVIDER: WebSearchProvider = DuckDuckGoSearchProvider()


def set_search_provider(provider: WebSearchProvider) -> None:
    """Set the active modular search provider."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider


def get_search_provider() -> WebSearchProvider:
    """Get the active modular search provider."""
    return _DEFAULT_PROVIDER


def search_web(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Execute search using active provider."""
    return _DEFAULT_PROVIDER.search(query=query, max_results=max_results)
