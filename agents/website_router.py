"""
Website Router

First-class routing decision: does this business have a working website?
Routes to Track A (website exists) or Track B (no website).
"""

import httpx
from rich.console import Console
from models.business import Business, WebsiteStatus
from models.lead import TrackType

console = Console()


class WebsiteRouter:
    """Validates website presence and routes to the correct analysis track."""

    async def route(self, business: Business) -> tuple[TrackType, Business]:
        """
        Validates the website URL and returns the resolved track + updated business.
        Even if a URL was found in the prospecting step, we confirm it's live.
        """
        if business.website_url:
            status = await self._probe_url(business.website_url)
            business = business.model_copy(update={"website_status": status})

        if business.website_status == WebsiteStatus.EXISTS:
            console.log(
                f"[green]Track A[/green] → {business.name} has a working website: {business.website_url}"
            )
            return TrackType.WEBSITE_EXISTS, business
        else:
            console.log(
                f"[yellow]Track B[/yellow] → {business.name} has no website (status: {business.website_status})"
            )
            return TrackType.NO_WEBSITE, business

    async def _probe_url(self, url: str) -> WebsiteStatus:
        """HEAD request to verify the URL resolves and returns a 2xx/3xx status."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.head(url)
                if resp.status_code < 400:
                    return WebsiteStatus.EXISTS
                return WebsiteStatus.BROKEN
        except Exception:
            return WebsiteStatus.BROKEN
