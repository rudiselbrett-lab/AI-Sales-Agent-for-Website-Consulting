"""
Business Prospecting Agent

Searches Google Maps for local SMBs by rotating through Charlotte
neighborhoods instead of just the city — surfaces businesses that
don't rank for broad city searches.
"""

import random
from rich.console import Console
from config import settings
from models.business import Business
from .google_maps_scraper import GoogleMapsScraper

console = Console()


class ProspectingAgent:

    def __init__(self):
        self.city = settings.target_city
        self.state = settings.target_state
        self.neighborhoods = settings.neighborhood_list
        self.scraper = GoogleMapsScraper()

    async def discover(self, industry: str, limit: int = 10) -> list[Business]:
        """
        Rotates through neighborhoods to find businesses that wouldn't
        appear in a broad Charlotte city search.
        """
        results: list[Business] = []
        seen_names: set[str] = set()

        # Shuffle neighborhoods so each run surfaces different areas
        neighborhoods = random.sample(self.neighborhoods, len(self.neighborhoods))

        for neighborhood in neighborhoods:
            if len(results) >= limit:
                break

            remaining = limit - len(results)
            location = f"{neighborhood}, {self.state}"
            console.log(f"[cyan]Searching:[/cyan] {industry} in {location}")

            batch = await self.scraper.search(
                query=industry,
                city=neighborhood,
                state=self.state,
                industry=industry,
                limit=remaining + 3,  # fetch a few extra to account for deduplication
            )

            for biz in batch:
                if biz.name not in seen_names:
                    seen_names.add(biz.name)
                    results.append(biz)
                    if len(results) >= limit:
                        break

        if not results:
            console.log(
                f"[red]No results for '{industry}' across all neighborhoods.[/red] "
                "Enable 'Show browser while scraping' to debug."
            )

        console.log(f"[green]Found {len(results)} unique '{industry}' businesses[/green]")
        return results
