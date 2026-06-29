"""
Google Maps Scraper

Scrapes Google Maps search results for local businesses using Playwright.
No API key required. Returns the same Business objects as the API-based prospector.

Searches: "{industry} in {city} {state}"
Extracts: name, address, phone, website, rating, review count
"""

import asyncio
import re
from rich.console import Console
from models.business import Business, WebsiteStatus

console = Console()


class GoogleMapsScraper:

    async def search(self, query: str, city: str, state: str, industry: str, limit: int = 20) -> list[Business]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            console.log("[red]Playwright not installed. Run: pip3 install playwright && playwright install chromium[/red]")
            return []

        businesses: list[Business] = []
        search_query = f"{query} in {city} {state}"
        console.log(f"[cyan]Scraping Google Maps:[/cyan] {search_query}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Block images/fonts to speed up scraping
            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())

            await page.goto(
                f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            # Dismiss cookie consent if present
            try:
                await page.click("button[aria-label='Accept all']", timeout=3000)
            except Exception:
                pass

            # Wait for results panel
            try:
                await page.wait_for_selector("div[role='feed']", timeout=10000)
            except Exception:
                console.log("[yellow]No results panel found — Google may have changed layout[/yellow]")
                await browser.close()
                return []

            # Scroll to load more results
            feed = page.locator("div[role='feed']")
            for _ in range(max(1, limit // 5)):
                await feed.evaluate("el => el.scrollTop = el.scrollHeight")
                await asyncio.sleep(1.5)

            # Collect all result cards
            cards = await page.locator("div[role='feed'] > div > div[jsaction]").all()
            console.log(f"Found {len(cards)} result cards")

            for card in cards[:limit]:
                try:
                    biz = await self._extract_from_card(card, page, city, state, industry)
                    if biz:
                        businesses.append(biz)
                except Exception as exc:
                    console.log(f"[dim]Card parse error: {exc}[/dim]")

            await browser.close()

        console.log(f"[green]Scraped {len(businesses)} businesses[/green]")
        return businesses

    async def _extract_from_card(self, card, page, city: str, state: str, industry: str) -> Business | None:
        # Click the card to open the detail panel
        try:
            await card.click()
            await asyncio.sleep(1.2)
        except Exception:
            return None

        # Extract from the detail side panel
        try:
            name = await page.locator("h1.DUwDvf").inner_text(timeout=3000)
        except Exception:
            return None

        if not name or len(name.strip()) < 2:
            return None

        name = name.strip()

        # Address
        address = None
        try:
            addr_el = page.locator("button[data-item-id='address']")
            if await addr_el.count() > 0:
                address = (await addr_el.get_attribute("aria-label") or "").replace("Address: ", "").strip()
        except Exception:
            pass

        # Phone
        phone = None
        try:
            phone_el = page.locator("button[data-item-id^='phone']")
            if await phone_el.count() > 0:
                phone_raw = await phone_el.get_attribute("aria-label") or ""
                phone = phone_raw.replace("Phone: ", "").strip()
        except Exception:
            pass

        # Website
        website_url = None
        try:
            web_el = page.locator("a[data-item-id='authority']")
            if await web_el.count() > 0:
                website_url = await web_el.get_attribute("href")
                # Strip Google redirect wrapper
                if website_url and "google.com/url" in website_url:
                    m = re.search(r"[?&]q=([^&]+)", website_url)
                    website_url = m.group(1) if m else website_url
        except Exception:
            pass

        # Rating + review count
        rating = None
        review_count = None
        try:
            rating_el = page.locator("div.F7nice span[aria-hidden='true']").first
            if await rating_el.count() > 0:
                rating_text = await rating_el.inner_text()
                rating = float(rating_text.replace(",", "."))
        except Exception:
            pass

        try:
            review_el = page.locator("div.F7nice span[aria-label*='review']").first
            if await review_el.count() > 0:
                label = await review_el.get_attribute("aria-label") or ""
                m = re.search(r"([\d,]+)", label)
                if m:
                    review_count = int(m.group(1).replace(",", ""))
        except Exception:
            pass

        return Business(
            name=name,
            industry=industry,
            city=city,
            state=state,
            phone=phone,
            address=address,
            website_url=website_url,
            website_status=WebsiteStatus.EXISTS if website_url else WebsiteStatus.NOT_FOUND,
            google_rating=rating,
            google_review_count=review_count,
        )
