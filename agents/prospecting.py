"""
Business Prospecting Agent

Discovers local SMBs in the target city using SerpAPI (Google Maps search).
Returns a list of Business objects with basic profile data populated.
"""

import httpx
import json
from rich.console import Console
from config import settings
from models.business import Business, WebsiteStatus

console = Console()


class ProspectingAgent:
    """Discovers SMBs in the target market via Google Maps / local search."""

    SERPAPI_BASE = "https://serpapi.com/search"

    def __init__(self):
        self.api_key = settings.serpapi_key
        self.city = settings.target_city
        self.state = settings.target_state

    async def discover(self, industry: str, limit: int = 25) -> list[Business]:
        """Return up to `limit` businesses for a given industry in the target city."""
        console.log(f"[cyan]Prospecting:[/cyan] searching '{industry}' in {self.city}, {self.state}")

        if not self.api_key:
            console.log("[yellow]No SERPAPI_KEY — returning mock data[/yellow]")
            return self._mock_businesses(industry, limit)

        params = {
            "engine": "google_maps",
            "q": f"{industry} in {self.city} {self.state}",
            "type": "search",
            "api_key": self.api_key,
            "num": limit,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.SERPAPI_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_results(data, industry)

    def _parse_results(self, data: dict, industry: str) -> list[Business]:
        businesses = []
        for result in data.get("local_results", []):
            website_url = result.get("website")
            businesses.append(
                Business(
                    name=result.get("title", "Unknown"),
                    industry=industry,
                    city=self.city,
                    state=self.state,
                    phone=result.get("phone"),
                    address=result.get("address"),
                    website_url=website_url,
                    website_status=WebsiteStatus.EXISTS if website_url else WebsiteStatus.NOT_FOUND,
                    google_place_id=result.get("place_id"),
                    google_rating=result.get("rating"),
                    google_review_count=result.get("reviews"),
                    google_categories=result.get("type", []) if isinstance(result.get("type"), list) else [],
                )
            )
        return businesses

    def _mock_businesses(self, industry: str, limit: int) -> list[Business]:
        """Returns deterministic mock data for development/testing without API keys."""
        mock = [
            Business(
                name=f"Charlotte {industry.title()} Co #{i+1}",
                industry=industry,
                city=self.city,
                state=self.state,
                phone=f"704-555-{1000+i:04d}",
                address=f"{100+i*10} Main St, {self.city}, {self.state}",
                website_url=f"https://example{i+1}.com" if i % 3 != 0 else None,
                website_status=WebsiteStatus.EXISTS if i % 3 != 0 else WebsiteStatus.NOT_FOUND,
                google_rating=round(3.5 + (i % 15) * 0.1, 1),
                google_review_count=i * 7 + 5,
                google_profile_complete=i % 2 == 0,
            )
            for i in range(min(limit, 10))
        ]
        return mock
