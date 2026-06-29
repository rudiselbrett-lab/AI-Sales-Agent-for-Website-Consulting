"""
Business Presence Reconstruction Agent (Track B)

For businesses with no website, reconstructs their digital footprint
from Google Business Profile data, Yelp, and directory signals.
Used as input for Digital Gap Analysis.
"""

import httpx
from rich.console import Console
from config import settings
from models.business import Business

console = Console()

COMMON_DIRECTORIES = ["yelp", "yellowpages", "bbb", "angi", "homeadvisor", "thumbtack", "nextdoor"]


class PresenceReconstructionAgent:
    """Enriches a no-website business with all available digital signals."""

    def __init__(self):
        self.serpapi_key = settings.serpapi_key

    async def reconstruct(self, business: Business) -> Business:
        """Enriches the business model with Google + directory presence signals."""
        console.log(f"[yellow]Reconstructing presence[/yellow] for {business.name}")

        updates: dict = {}

        gbp_data = await self._fetch_google_profile(business)
        updates.update(gbp_data)

        yelp_data = await self._probe_yelp(business)
        updates.update(yelp_data)

        updates["in_other_directories"] = await self._check_directories(business)

        return business.model_copy(update=updates)

    async def _fetch_google_profile(self, business: Business) -> dict:
        """Fetches enhanced GBP data via SerpAPI local results."""
        if not self.serpapi_key:
            return {
                "google_profile_complete": business.google_rating is not None,
                "google_review_count": business.google_review_count or 0,
            }

        params = {
            "engine": "google_maps",
            "q": f"{business.name} {business.address or business.city}",
            "type": "search",
            "api_key": self.serpapi_key,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                data = resp.json()

            results = data.get("local_results", [])
            if not results:
                return {}

            top = results[0]
            hours = top.get("hours")
            photos = top.get("photos_count", 0)
            posts = top.get("posts")

            missing_fields = []
            if not top.get("phone"):
                missing_fields.append("phone number")
            if not top.get("website"):
                missing_fields.append("website")
            if not hours:
                missing_fields.append("business hours")
            if not photos:
                missing_fields.append("photos")
            if not top.get("description"):
                missing_fields.append("business description")

            completeness = max(0, 100 - len(missing_fields) * 20)

            return {
                "google_rating": top.get("rating"),
                "google_review_count": top.get("reviews"),
                "google_profile_complete": completeness >= 80,
                "google_categories": top.get("type", []) if isinstance(top.get("type"), list) else [],
            }
        except Exception as exc:
            console.log(f"[dim]GBP fetch failed: {exc}[/dim]")
            return {}

    async def _probe_yelp(self, business: Business) -> dict:
        """Checks for a Yelp listing via search."""
        if not self.serpapi_key:
            return {}

        params = {
            "engine": "google",
            "q": f'site:yelp.com "{business.name}" {business.city}',
            "api_key": self.serpapi_key,
            "num": 3,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                data = resp.json()

            for result in data.get("organic_results", []):
                if "yelp.com/biz/" in result.get("link", ""):
                    return {"yelp_url": result["link"]}
        except Exception:
            pass
        return {}

    async def _check_directories(self, business: Business) -> list[str]:
        """Returns list of directories where the business has a presence."""
        if not self.serpapi_key:
            return []

        found = []
        params = {
            "engine": "google",
            "q": f'"{business.name}" {business.city} {business.state}',
            "api_key": self.serpapi_key,
            "num": 10,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                data = resp.json()

            for result in data.get("organic_results", []):
                link = result.get("link", "")
                for directory in COMMON_DIRECTORIES:
                    if directory in link and directory not in found:
                        found.append(directory)
        except Exception:
            pass
        return found
