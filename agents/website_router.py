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

            # Pull out search results as (url, surrounding_text) pairs
            # Google wraps links as <a href="/url?q=..."> with nearby title/snippet text
            results = self._extract_search_results(html)

            for candidate_url, context_text in results:
                domain = self._extract_domain(candidate_url)
                if not domain:
                    continue

                # Skip directories and social sites
                if any(skip in domain for skip in SKIP_DOMAINS):
                    continue

                if "google." in domain:
                    continue

                # Accept if domain matches business name OR if the page context
                # (title/snippet) mentions the business name — catches branded domains
                # like ncbd.us for "Nichols Custom Builders Design"
                domain_ok = self._domain_matches_business(domain, business.name)
                context_ok = self._context_mentions_business(context_text, business.name)

                if not domain_ok and not context_ok:
                    continue

                status = await self._probe_url(candidate_url)
                if status == WebsiteStatus.EXISTS:
                    return candidate_url

        except Exception as exc:
            console.log(f"[dim]Google search fallback failed for {business.name}: {exc}[/dim]")

        return None

    def _extract_search_results(self, html: str) -> list[tuple[str, str]]:
        """Returns list of (url, context_text) from Google search HTML."""
        results = []
        # Find all href URLs and grab surrounding text (±200 chars) as context
        for m in re.finditer(r'href="(https?://[^"]+)"', html):
            raw_url = m.group(1)
            if "google.com/url" in raw_url:
                q = re.search(r"[?&]q=(https?://[^&]+)", raw_url)
                url = q.group(1) if q else raw_url
            else:
                url = raw_url
            start = max(0, m.start() - 200)
            end = min(len(html), m.end() + 200)
            context = re.sub(r"<[^>]+>", " ", html[start:end])  # strip tags
            results.append((url, context))
        return results

    def _context_mentions_business(self, context: str, business_name: str) -> bool:
        """Returns True if the search result snippet mentions the business name."""
        stop_words = {"the", "and", "of", "a", "an", "in", "at", "for",
                      "llc", "inc", "co", "company", "services", "service"}
        name_words = re.sub(r"[^a-z0-9\s]", "", business_name.lower()).split()
        meaningful = [w for w in name_words if w not in stop_words and len(w) > 2]
        context_lower = context.lower()
        # Require at least 2 meaningful words to appear in the snippet
        matches = sum(1 for w in meaningful if w in context_lower)
        return matches >= min(2, len(meaningful))

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
