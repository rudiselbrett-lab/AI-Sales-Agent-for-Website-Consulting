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
        import datetime
        html = crawl.pages.get("/", "")
        soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")
        current_year = datetime.datetime.now().year

        # ── Staleness detection ──────────────────────────────────────────────
        copyright_year = self._detect_copyright_year(soup, html)
        outdated_tech = self._detect_outdated_tech(soup, html)
        has_mobile_viewport = bool(soup.find("meta", attrs={"name": "viewport"}))

        staleness_reasons = []
        if copyright_year and copyright_year < current_year - 3:
            staleness_reasons.append(f"Copyright year shows {copyright_year} — likely {current_year - copyright_year}+ years without an update")
        if outdated_tech:
            staleness_reasons.append("Uses outdated web technology (Flash / old jQuery)")
        if not has_mobile_viewport:
            staleness_reasons.append("No mobile viewport tag — site may not be mobile-friendly")
        if not crawl.is_https:
            staleness_reasons.append("Still on HTTP (not HTTPS) — browser security warnings likely")

        stale_years = settings.stale_site_years
        is_stale = (copyright_year is not None and copyright_year < current_year - stale_years) or \
                   (len(staleness_reasons) >= 3)

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
            # Staleness
            "copyright_year": copyright_year,
            "is_stale": is_stale,
            "staleness_reasons": staleness_reasons,
            "uses_outdated_tech": outdated_tech,
            "has_mobile_viewport": has_mobile_viewport,
        }

    def _detect_copyright_year(self, soup, html: str) -> int | None:
        import re, datetime
        current_year = datetime.datetime.now().year
        # Look in footer first, then full page
        footer = soup.find("footer") or soup
        text = footer.get_text(" ", strip=True)
        # Match patterns like © 2019, Copyright 2019, 2015-2019
        matches = re.findall(r"(?:©|copyright|\(c\))[^\d]*(\d{4})", text.lower())
        # Also catch year ranges: 2015–2023 → take the last year
        range_matches = re.findall(r"(\d{4})\s*[-–—]\s*(\d{4})", text)
        years = [int(y) for y in matches if 1990 <= int(y) <= current_year]
        for start, end in range_matches:
            if 1990 <= int(end) <= current_year:
                years.append(int(end))
        return max(years) if years else None

    def _detect_outdated_tech(self, soup, html: str) -> bool:
        # Flash
        if soup.find("object", attrs={"type": "application/x-shockwave-flash"}):
            return True
        if "swfobject" in html.lower() or ".swf" in html.lower():
            return True
        # Very old jQuery (1.x)
        import re
        old_jquery = re.search(r'jquery[.-]1\.[0-6]\.', html.lower())
        if old_jquery:
            return True
        return False

    async def _ai_score(
        self, business: Business, signals: dict, crawl: CrawlResult
    ) -> WebsiteAnalysis:
        if not settings.anthropic_api_key:
            return self._heuristic_score(business, signals)

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

        return self._build_analysis(business, signals, ai_data)

    def _heuristic_score(self, business: Business, signals: dict) -> WebsiteAnalysis:
        """Heuristic scoring with staleness detection — no API key required."""
        import datetime
        current_year = datetime.datetime.now().year
        score = 60
        issues, wins = [], []

        # ── Staleness (biggest deductions) ───────────────────────────────────
        stale_threshold = settings.stale_site_years  # default 10
        copyright_year = signals.get("copyright_year")
        if copyright_year:
            age = current_year - copyright_year
            if age >= stale_threshold:
                score -= 30
                issues.append(f"Website last updated around {copyright_year} — {age} years old, severely outdated")
            elif age >= stale_threshold // 2:
                score -= 10
                issues.append(f"Copyright shows {copyright_year} — site is aging and may need a refresh")

        if signals.get("uses_outdated_tech"):
            score -= 15
            issues.append("Uses outdated technology (Flash or old JavaScript libraries)")

        if not signals.get("has_mobile_viewport"):
            score -= 15
            issues.append("Not optimised for mobile — likely breaks on phones")
            wins.append("Add a mobile-responsive design or rebuild with a modern template")

        # ── Trust / security ──────────────────────────────────────────────────
        if not signals["has_ssl"]:
            score -= 10
            issues.append("No HTTPS — Chrome shows a 'Not Secure' warning to visitors")
            wins.append("Switch to HTTPS (usually free via Let's Encrypt)")

        # ── Conversion ────────────────────────────────────────────────────────
        if not signals["has_contact_form"] and not signals["has_phone_cta"]:
            score -= 10
            issues.append("No clear way to contact or call from the site")
            wins.append("Add a click-to-call button and simple contact form")

        # ── SEO basics ────────────────────────────────────────────────────────
        if not signals["has_title_tag"]:
            score -= 8
            issues.append("Missing page title — hurts Google ranking")
            wins.append("Add a descriptive title tag to every page")
        if not signals["has_meta_description"]:
            score -= 4
            wins.append("Add meta descriptions to improve click-through from search results")
        if not signals["has_h1"]:
            score -= 4
            issues.append("No H1 heading — search engines can't identify the main topic")

        # ── Speed ─────────────────────────────────────────────────────────────
        if signals["load_time_seconds"] and signals["load_time_seconds"] > 3:
            score -= 8
            issues.append(f"Slow load time ({signals['load_time_seconds']}s) — visitors drop off after 3s")
            wins.append("Compress images and enable caching to improve load speed")

        score = max(5, min(100, score))

        # ── Plain-English summary ─────────────────────────────────────────────
        if score >= 70:
            verdict = "reasonably modern"
        elif score >= 50:
            verdict = "functional but showing its age"
        elif score >= 30:
            verdict = "significantly outdated"
        else:
            verdict = "severely outdated and likely hurting the business"

        year_note = f" Last updated around {copyright_year}." if copyright_year else ""
        summary = (
            f"{business.name}'s website is {verdict}.{year_note} "
            f"{'It is not mobile-friendly, which affects the majority of local search visitors. ' if not signals.get('has_mobile_viewport') else ''}"
            f"Found {len(issues)} issue{'s' if len(issues) != 1 else ''} that are likely costing them inbound leads."
        )

        return self._build_analysis(business, signals, {
            "website_score": score,
            "summary": summary,
            "top_issues": issues[:4],
            "quick_wins": wins[:3],
            "mobile_friendly": signals.get("has_mobile_viewport", False),
            "has_clear_services_page": signals["has_services_page"],
            "last_updated_estimate": str(copyright_year) if copyright_year else None,
        })

    def _build_analysis(self, business: Business, signals: dict, ai_data: dict) -> WebsiteAnalysis:
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
            has_clear_services_page=ai_data.get("has_clear_services_page", signals.get("has_services_page", False)),
            has_about_page=signals["has_about_page"],
            has_testimonials=signals["has_testimonials"],
            image_count=signals["image_count"],
            has_lazy_loading=signals["has_lazy_loading"],
            load_time_seconds=signals["load_time_seconds"],
            page_count_estimate=signals["page_count_crawled"],
            mobile_friendly=ai_data.get("mobile_friendly", signals.get("has_mobile_viewport", False)),
            last_updated_estimate=ai_data.get("last_updated_estimate"),
            # Staleness fields
            copyright_year=signals.get("copyright_year"),
            is_stale=signals.get("is_stale", False),
            staleness_reasons=signals.get("staleness_reasons", []),
            uses_outdated_tech=signals.get("uses_outdated_tech", False),
            has_mobile_viewport=signals.get("has_mobile_viewport", False),
            summary=ai_data.get("summary", ""),
            top_issues=ai_data.get("top_issues", []),
            quick_wins=ai_data.get("quick_wins", []),
            website_score=ai_data.get("website_score", 50),
        )
