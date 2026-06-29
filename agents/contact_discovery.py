"""
Contact Discovery Agent

Attempts to find an owner name and email for a business using:
1. Hunter.io domain search (Track A — website businesses)
2. Google search heuristics (Track B — no-website businesses)
"""

import httpx
from rich.console import Console
from config import settings
from models.business import Business

console = Console()


class ContactDiscoveryAgent:

    def __init__(self):
        self.hunter_key = settings.hunter_api_key

    async def discover(self, business: Business) -> Business:
        """Enriches business with owner name + email if discoverable."""
        if business.website_url and self.hunter_key:
            updates = await self._hunter_lookup(business)
        else:
            updates = await self._google_heuristic(business)

        if updates:
            business = business.model_copy(update=updates)
            console.log(
                f"[cyan]Contact found[/cyan] {business.name}: "
                f"{business.owner_name or 'name unknown'} / "
                f"{business.owner_email or 'no email'}"
            )
        else:
            console.log(f"[dim]No contact found for {business.name}[/dim]")

        return business

    async def _hunter_lookup(self, business: Business) -> dict:
        domain = self._extract_domain(business.website_url or "")
        if not domain:
            return {}

        url = "https://api.hunter.io/v2/domain-search"
        params = {"domain": domain, "api_key": self.hunter_key, "limit": 5, "type": "personal"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

            emails = data.get("data", {}).get("emails", [])
            # Prefer owner/founder roles
            priority_roles = {"owner", "founder", "president", "ceo", "manager", "director"}
            for entry in emails:
                position = (entry.get("position") or "").lower()
                if any(role in position for role in priority_roles):
                    return {
                        "owner_name": f"{entry.get('first_name', '')} {entry.get('last_name', '')}".strip(),
                        "owner_email": entry.get("value"),
                        "contact_confidence": entry.get("confidence", 0) / 100,
                    }

            # Fallback to first email
            if emails:
                entry = emails[0]
                return {
                    "owner_name": f"{entry.get('first_name', '')} {entry.get('last_name', '')}".strip(),
                    "owner_email": entry.get("value"),
                    "contact_confidence": entry.get("confidence", 0) / 100,
                }
        except Exception as exc:
            console.log(f"[dim]Hunter lookup failed: {exc}[/dim]")
        return {}

    async def _google_heuristic(self, business: Business) -> dict:
        """For no-website businesses: attempts name discovery via search snippet."""
        if not settings.serpapi_key:
            return {}

        query = f'"{business.name}" owner OR "owned by" {business.city}'
        params = {
            "engine": "google",
            "q": query,
            "api_key": settings.serpapi_key,
            "num": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                data = resp.json()

            for result in data.get("organic_results", []):
                snippet = result.get("snippet", "")
                # Very basic heuristic — a more robust approach would use NLP/Claude
                for trigger in ["owned by", "owner", "proprietor"]:
                    if trigger in snippet.lower():
                        # Extract 2-3 words after the trigger as potential name
                        idx = snippet.lower().index(trigger) + len(trigger)
                        candidate = snippet[idx:idx+30].strip().split(",")[0].strip()
                        if 3 < len(candidate) < 40 and " " in candidate:
                            return {"owner_name": candidate, "contact_confidence": 0.3}
        except Exception:
            pass
        return {}

    def _extract_domain(self, url: str) -> str:
        import re
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        return match.group(1) if match else ""
