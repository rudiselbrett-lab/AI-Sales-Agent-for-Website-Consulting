"""
Google Maps Scraper

Scrapes Google Maps for local SMBs using Playwright.
No API key required.

Strategy:
  1. Load the Maps search results feed
  2. Parse business name / rating / address from each card's aria-label
     (stable — Google keeps these for accessibility)
  3. Click each card only to grab the website URL from the detail panel
  4. Return Business objects

Debug mode: set headless=False to watch the browser in real time.
Screenshots are saved to ./data/debug/ on any failure.
"""

import asyncio
import re
from pathlib import Path
from rich.console import Console
from models.business import Business, WebsiteStatus

console = Console()
DEBUG_DIR = Path("./data/debug")


class GoogleMapsScraper:

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo  # ms between actions — set 500+ to watch it work

    async def search(
        self,
        query: str,
        city: str,
        state: str,
        industry: str,
        limit: int = 20,
    ) -> list[Business]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            console.log(
                "[red]Playwright not installed.[/red]\n"
                "Run: pip3 install playwright && python3 -m playwright install chromium"
            )
            return []

        search_query = f"{query} in {city} {state}"
        console.log(f"[cyan]Google Maps scrape:[/cyan] '{search_query}' (limit {limit})")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # Block media to speed up loading
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
                lambda r: r.abort(),
            )

            url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                console.log(f"[red]Failed to load Maps:[/red] {exc}")
                await browser.close()
                return []

            # Dismiss consent dialogs (EU / cookie banners)
            for label in ["Accept all", "Reject all", "I agree", "Agree"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.count() > 0:
                        await btn.first.click(timeout=2000)
                        await asyncio.sleep(0.5)
                        break
                except Exception:
                    pass

            # Wait for the results feed
            try:
                await page.wait_for_selector("div[role='feed']", timeout=12000)
            except Exception:
                await self._screenshot(page, "no_feed")
                console.log(
                    "[yellow]Results feed not found.[/yellow] "
                    "Screenshot saved to data/debug/. "
                    "Google may have changed layout or detected the bot."
                )
                await browser.close()
                return []

            # Scroll the feed to load more results
            await self._scroll_feed(page, target=limit)

            # Step 1: extract business cards from the list (name, rating, address)
            cards = await self._parse_list(page, industry, city, state)
            console.log(f"Parsed {len(cards)} businesses from list")

            # Step 2: click each card to get website URL
            businesses: list[Business] = []
            for i, biz in enumerate(cards[:limit]):
                try:
                    biz = await self._enrich_with_website(page, biz, i)
                except Exception as exc:
                    console.log(f"[dim]Website enrichment failed for {biz.name}: {exc}[/dim]")
                businesses.append(biz)
                await asyncio.sleep(0.3)

            await browser.close()

        console.log(
            f"[green]Done:[/green] {len(businesses)} businesses — "
            f"{sum(1 for b in businesses if b.has_website)} have websites, "
            f"{sum(1 for b in businesses if not b.has_website)} don't"
        )
        return businesses

    # ── Feed scrolling ────────────────────────────────────────────────────────

    async def _scroll_feed(self, page, target: int) -> None:
        feed = page.locator("div[role='feed']")
        scrolls = max(2, target // 5)
        for _ in range(scrolls):
            await feed.evaluate("el => el.scrollTop = el.scrollHeight")
            await asyncio.sleep(1.2)

    # ── List parsing (no clicks) ───────────────────────────────────────────────

    async def _parse_list(self, page, industry: str, city: str, state: str) -> list[Business]:
        """
        Each result card in the feed has an <a> with an aria-label like:
          "Joe's Plumbing. 4.3 stars. 58 reviews. Plumber. 123 Main St, Charlotte, NC"
        This is the most stable extraction point — Google keeps aria-labels for accessibility.
        """
        businesses: list[Business] = []

        # Primary: grab aria-labels from result links
        links = await page.locator("div[role='feed'] a[aria-label]").all()

        seen: set[str] = set()
        for link in links:
            label = (await link.get_attribute("aria-label") or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)

            biz = self._parse_aria_label(label, industry, city, state)
            if biz:
                businesses.append(biz)

        # Fallback: try text content of each card if aria approach yielded nothing
        if not businesses:
            console.log("[dim]aria-label parse yielded nothing — trying text fallback[/dim]")
            businesses = await self._text_fallback(page, industry, city, state)

        return businesses

    def _parse_aria_label(
        self, label: str, industry: str, city: str, state: str
    ) -> Business | None:
        """
        Parses: "Name. 4.3 stars. 58 reviews. Category. 123 Main St, Charlotte, NC"
        All fields after Name are optional.
        """
        parts = [p.strip() for p in label.split(".") if p.strip()]
        if not parts or len(parts[0]) < 2:
            return None

        name = parts[0]

        # Skip if it looks like a UI element, not a business
        if any(skip in name.lower() for skip in ["directions", "save", "share", "website", "call"]):
            return None

        rating = None
        review_count = None
        address = None

        for part in parts[1:]:
            # Rating: "4.3 stars"
            if "star" in part.lower():
                m = re.search(r"(\d+[\.,]\d+)", part)
                if m:
                    try:
                        rating = float(m.group(1).replace(",", "."))
                    except ValueError:
                        pass

            # Review count: "58 reviews"
            elif "review" in part.lower():
                m = re.search(r"([\d,]+)", part)
                if m:
                    try:
                        review_count = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass

            # Address heuristic: contains digits or city name
            elif re.search(r"\d", part) or city.lower() in part.lower():
                address = part

        return Business(
            name=name,
            industry=industry,
            city=city,
            state=state,
            address=address,
            google_rating=rating,
            google_review_count=review_count,
            website_status=WebsiteStatus.NOT_FOUND,  # enriched later
        )

    async def _text_fallback(
        self, page, industry: str, city: str, state: str
    ) -> list[Business]:
        """Last resort: grab visible text from each card."""
        businesses = []
        cards = await page.locator("div[role='feed'] > div").all()
        for card in cards:
            try:
                text = (await card.inner_text()).strip()
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if lines and len(lines[0]) > 2:
                    businesses.append(
                        Business(
                            name=lines[0],
                            industry=industry,
                            city=city,
                            state=state,
                            website_status=WebsiteStatus.NOT_FOUND,
                        )
                    )
            except Exception:
                pass
        return businesses

    # ── Website enrichment (one click per card) ───────────────────────────────

    async def _enrich_with_website(self, page, biz: Business, index: int) -> Business:
        """Click the card for this business to get its website URL from the detail panel."""
        # Find the card by matching the business name in aria-label
        card = page.locator(
            f"div[role='feed'] a[aria-label^='{self._escape_selector(biz.name)}']"
        ).first

        if await card.count() == 0:
            return biz

        await card.click()
        await asyncio.sleep(1.5)

        # Website link in detail panel — data-item-id is stable
        website_url = None

        # Try the "Website" action button first (most reliable)
        for selector in [
            "a[data-item-id='authority']",
            "a[aria-label^='Website']",
            "a[aria-label*='website']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    href = await el.get_attribute("href") or ""
                    if href and not href.startswith("https://www.google"):
                        website_url = self._clean_url(href)
                        break
            except Exception:
                pass

        # Phone while we're here
        phone = None
        for selector in [
            "button[data-item-id^='phone']",
            "button[aria-label^='Phone']",
        ]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    label = await el.get_attribute("aria-label") or ""
                    phone = label.replace("Phone:", "").replace("Phone: ", "").strip()
                    if phone:
                        break
            except Exception:
                pass

        return biz.model_copy(update={
            "website_url": website_url,
            "website_status": WebsiteStatus.EXISTS if website_url else WebsiteStatus.NOT_FOUND,
            "phone": phone or biz.phone,
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clean_url(self, url: str) -> str:
        if "google.com/url" in url:
            m = re.search(r"[?&]q=([^&]+)", url)
            return m.group(1) if m else url
        return url

    def _escape_selector(self, name: str) -> str:
        return name.replace("'", "\\'").replace('"', '\\"')[:40]

    async def _screenshot(self, page, label: str) -> None:
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            path = DEBUG_DIR / f"{label}.png"
            await page.screenshot(path=str(path), full_page=False)
            console.log(f"[dim]Screenshot saved: {path}[/dim]")
        except Exception:
            pass
