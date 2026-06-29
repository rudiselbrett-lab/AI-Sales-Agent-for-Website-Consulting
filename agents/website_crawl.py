"""
Website Crawl Agent

Fetches the homepage and key pages, extracting raw signals needed
for the Website Analysis agent (Track A).
"""

import time
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from models.business import Business

console = Console()

PAGES_TO_PROBE = ["", "/services", "/about", "/contact", "/sitemap.xml"]


class CrawlResult:
    def __init__(self):
        self.pages: dict[str, str] = {}          # path → html
        self.status_codes: dict[str, int] = {}
        self.load_time_seconds: float | None = None
        self.final_url: str = ""
        self.is_https: bool = False


class WebsiteCrawlAgent:
    """Crawls the business website and returns raw HTML for analysis."""

    async def crawl(self, business: Business) -> CrawlResult | None:
        if not business.website_url:
            return None

        result = CrawlResult()
        result.is_https = business.website_url.startswith("https://")

        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SalesAuditBot/1.0)"},
        ) as client:
            for path in PAGES_TO_PROBE:
                url = business.website_url.rstrip("/") + path
                try:
                    start = time.monotonic()
                    resp = await client.get(url)
                    elapsed = time.monotonic() - start

                    result.status_codes[path or "/"] = resp.status_code
                    if resp.status_code == 200:
                        result.pages[path or "/"] = resp.text
                        if not result.load_time_seconds:
                            result.load_time_seconds = round(elapsed, 2)
                            result.final_url = str(resp.url)
                except Exception as exc:
                    console.log(f"[dim]Crawl skip {url}: {exc}[/dim]")

        console.log(
            f"[cyan]Crawled[/cyan] {business.name}: {len(result.pages)} pages fetched"
        )
        return result
