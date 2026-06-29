"""
Website Analysis Agent (Track A)

Takes raw crawl data, runs heuristic extraction, then uses Claude
to generate a narrative summary, surface top issues, and assign a score.
"""

import json
from bs4 import BeautifulSoup
import anthropic
from rich.console import Console
from config import settings
from models.business import Business
from models.analysis import WebsiteAnalysis
from .website_crawl import CrawlResult

console = Console()


class WebsiteAnalysisAgent:

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def analyze(self, business: Business, crawl: CrawlResult) -> WebsiteAnalysis:
        signals = self._extract_signals(crawl)
        analysis = await self._ai_score(business, signals, crawl)
        console.log(
            f"[green]Website score[/green] {business.name}: {analysis.website_score}/100"
        )
        return analysis

    def _extract_signals(self, crawl: CrawlResult) -> dict:
        html = crawl.pages.get("/", "")
        soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")

        return {
            "has_title_tag": bool(soup.find("title") and soup.find("title").get_text(strip=True)),
            "has_meta_description": bool(soup.find("meta", attrs={"name": "description"})),
            "has_h1": bool(soup.find("h1")),
            "has_schema_markup": bool(soup.find("script", attrs={"type": "application/ld+json"})),
            "has_contact_form": bool(soup.find("form")),
            "has_phone_cta": bool(soup.find(string=lambda t: t and ("call" in t.lower() or "phone" in t.lower()))),
            "has_google_maps_embed": "google.com/maps" in html or "maps.googleapis" in html,
            "has_ssl": crawl.is_https,
            "has_sitemap": "/sitemap.xml" in crawl.status_codes and crawl.status_codes.get("/sitemap.xml") == 200,
            "has_services_page": "/services" in crawl.status_codes and crawl.status_codes.get("/services") == 200,
            "has_about_page": "/about" in crawl.status_codes and crawl.status_codes.get("/about") == 200,
            "image_count": len(soup.find_all("img")),
            "has_lazy_loading": any(img.get("loading") == "lazy" for img in soup.find_all("img")),
            "load_time_seconds": crawl.load_time_seconds,
            "has_testimonials": bool(
                soup.find(string=lambda t: t and any(w in t.lower() for w in ["testimonial", "review", "customer said"]))
            ),
            "page_count_crawled": len(crawl.pages),
        }

    async def _ai_score(
        self, business: Business, signals: dict, crawl: CrawlResult
    ) -> WebsiteAnalysis:
        homepage_snippet = crawl.pages.get("/", "")[:3000]

        prompt = f"""You are a website conversion and SEO auditor evaluating a local service business website.

Business: {business.name} ({business.industry}) — {business.location}
Website: {business.website_url}

Extracted signals:
{json.dumps(signals, indent=2)}

Homepage HTML snippet (first 3000 chars):
{homepage_snippet}

Return a JSON object with these exact keys:
{{
  "website_score": <integer 0-100>,
  "summary": "<2-3 sentence plain-English summary of the site's overall quality>",
  "top_issues": ["<issue 1>", "<issue 2>", "<issue 3>"],
  "quick_wins": ["<win 1>", "<win 2>", "<win 3>"],
  "mobile_friendly": <true|false>,
  "has_clear_services_page": <true|false>,
  "last_updated_estimate": "<rough estimate like '2022 or older' based on copyright notices or content>"
}}

Scoring guidance (0–100):
- 80–100: Modern, fast, clear CTA, good SEO basics, mobile-friendly
- 60–79: Functional but missing key conversion elements
- 40–59: Significant gaps — missing pages, poor mobile, no CTA
- 20–39: Major problems — outdated, broken elements, no contact info
- 0–19: Barely functional or worse than nothing
"""

        response = self.client.messages.create(
            model=settings.agent_model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        # Extract JSON from possible markdown code block
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            ai_data = json.loads(raw)
        except json.JSONDecodeError:
            ai_data = {}

        return WebsiteAnalysis(
            url=business.website_url or "",
            has_title_tag=signals["has_title_tag"],
            has_meta_description=signals["has_meta_description"],
            has_h1=signals["has_h1"],
            has_schema_markup=signals["has_schema_markup"],
            has_contact_form=signals["has_contact_form"],
            has_phone_cta=signals["has_phone_cta"],
            has_google_maps_embed=signals["has_google_maps_embed"],
            has_ssl=signals["has_ssl"],
            has_sitemap=signals["has_sitemap"],
            has_clear_services_page=ai_data.get("has_clear_services_page", signals["has_services_page"]),
            has_about_page=signals["has_about_page"],
            has_testimonials=signals["has_testimonials"],
            image_count=signals["image_count"],
            has_lazy_loading=signals["has_lazy_loading"],
            load_time_seconds=signals["load_time_seconds"],
            page_count_estimate=signals["page_count_crawled"],
            mobile_friendly=ai_data.get("mobile_friendly", False),
            last_updated_estimate=ai_data.get("last_updated_estimate"),
            summary=ai_data.get("summary", ""),
            top_issues=ai_data.get("top_issues", []),
            quick_wins=ai_data.get("quick_wins", []),
            website_score=ai_data.get("website_score", 50),
        )
