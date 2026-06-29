"""
Business Prospecting Agent

Primary: scrapes Google Maps via Playwright (no API key required)
Fallback: SerpAPI if SERPAPI_KEY is set
Dev fallback: mock data if neither is available
"""

import httpx
from rich.console import Console
from config import settings
from models.business import Business, WebsiteStatus
from .google_maps_scraper import GoogleMapsScraper

console = Console()


class ProspectingAgent:

    def __init__(self):
        self.city = settings.target_city
        self.state = settings.target_state
        self.scraper = GoogleMapsScraper()

    async def discover(self, industry: str, limit: int = 25) -> list[Business]:
        console.log(f"[cyan]Prospecting:[/cyan] '{industry}' in {self.city}, {self.state}")

        # Primary: Playwright scraper (free, no key needed)
        try:
            results = await self.scraper.search(
                query=industry,
                city=self.city,
                state=self.state,
                industry=industry,
                limit=limit,
            )
            if results:
                return results
        except Exception as exc:
            console.log(f"[yellow]Scraper failed ({exc}) — trying SerpAPI fallback[/yellow]")

        # Fallback: SerpAPI
        if settings.serpapi_key:
            return await self._serpapi_search(industry, limit)

        # Dev fallback: mock data
        console.log("[yellow]No scraper or API available — using mock data[/yellow]")
        return self._mock_businesses(industry, limit)

    async def _serpapi_search(self, industry: str, limit: int) -> list[Business]:
        params = {
            "engine": "google_maps",
            "q": f"{industry} in {self.city} {self.state}",
            "type": "search",
            "api_key": settings.serpapi_key,
            "num": limit,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://serpapi.com/search", params=params)
            resp.raise_for_status()
            data = resp.json()

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
                )
            )
        return businesses

    def _mock_businesses(self, industry: str, limit: int) -> list[Business]:
        return [
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
