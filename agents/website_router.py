"""
Website Router

Routing decision: does this business have a working website?

Verification order:
  1. URL from Google Maps scraper → HEAD probe to confirm it's live
  2. If no URL found → Google search fallback to find a website
  3. Only routes to Track B (no website) if both come up empty
"""

import re
import httpx
from rich.console import Console
from models.business import Business, WebsiteStatus
from models.lead import TrackType

console = Console()

# Domains to ignore in Google search results — not the business's own site
SKIP_DOMAINS = {
    "google.com", "yelp.com", "facebook.com", "instagram.com",
    "yellowpages.com", "bbb.org", "angi.com", "homeadvisor.com",
    "thumbtack.com", "nextdoor.com", "linkedin.com", "mapquest.com",
    "tripadvisor.com", "foursquare.com", "houzz.com", "angieslist.com",
}


class WebsiteRouter:

    async def route(self, business: Business) -> tuple[TrackType, Business]:
        # Step 1: if scraper found a URL, verify it's actually live
        if business.website_url:
            status = await self._probe_url(business.website_url)
            business = business.model_copy(update={"website_status": status})

        # Step 2: if no URL (or broken), try Google search as fallback
        if business.website_status != WebsiteStatus.EXISTS:
            found_url = await self._google_search_fallback(business)
            if found_url:
                business = business.model_copy(update={
                    "website_url": found_url,
                    "website_status": WebsiteStatus.EXISTS,
                })
                console.log(
                    f"[green]Found via Google search:[/green] {business.name} → {found_url}"
                )

        if business.website_status == WebsiteStatus.EXISTS:
            console.log(f"[green]Track A[/green] → {business.name} | {business.website_url}")
            return TrackType.WEBSITE_EXISTS, business
        else:
            console.log(f"[yellow]Track B[/yellow] → {business.name} | no website confirmed")
            return TrackType.NO_WEBSITE, business

    async def _probe_url(self, url: str) -> WebsiteStatus:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.head(url)
                return WebsiteStatus.EXISTS if resp.status_code < 400 else WebsiteStatus.BROKEN
        except Exception:
            return WebsiteStatus.BROKEN

    async def _google_search_fallback(self, business: Business) -> str | None:
        """
        Searches Google for the business name + city and returns the first
        result URL that looks like the business's own website.
        """
        query = f'"{business.name}" {business.city} {business.state}'
        url = "https://www.google.com/search"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        }
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url, params={"q": query, "num": 10})
                html = resp.text

            # Extract href values from search result links
            # Google wraps organic results in <a href="/url?q=..."> or direct hrefs
            candidates = re.findall(r'href="(https?://[^"]+)"', html)

            for candidate in candidates:
                # Strip Google redirect wrappers
                if "google.com/url" in candidate:
                    m = re.search(r"[?&]q=(https?://[^&]+)", candidate)
                    candidate = m.group(1) if m else candidate

                domain = self._extract_domain(candidate)
                if not domain:
                    continue

                # Skip known directory/social sites
                if any(skip in domain for skip in SKIP_DOMAINS):
                    continue

                # Skip Google's own domains
                if "google." in domain:
                    continue

                # Only accept if the domain looks like it belongs to this business
                if not self._domain_matches_business(domain, business.name):
                    continue

                # Confirm the site is live
                status = await self._probe_url(candidate)
                if status == WebsiteStatus.EXISTS:
                    return candidate

        except Exception as exc:
            console.log(f"[dim]Google search fallback failed for {business.name}: {exc}[/dim]")

        return None

    def _domain_matches_business(self, domain: str, business_name: str) -> bool:
        """
        Returns True only if the domain plausibly belongs to this business.
        Checks whether meaningful words from the business name appear in the domain.
        """
        # Normalize: lowercase, strip punctuation, split into words
        stop_words = {"the", "and", "of", "a", "an", "in", "at", "for",
                      "llc", "inc", "co", "company", "services", "service",
                      "group", "solutions", "professionals", "pros"}

        name_words = re.sub(r"[^a-z0-9\s]", "", business_name.lower()).split()
        meaningful = [w for w in name_words if w not in stop_words and len(w) > 2]

        if not meaningful:
            return False

        domain_clean = re.sub(r"\.[^.]+$", "", domain.lower())  # strip TLD

        # At least one meaningful word from the business name must appear in the domain
        return any(word in domain_clean for word in meaningful)

    def _extract_domain(self, url: str) -> str:
        m = re.search(r"https?://(?:www\.)?([^/?#]+)", url)
        return m.group(1).lower() if m else ""
