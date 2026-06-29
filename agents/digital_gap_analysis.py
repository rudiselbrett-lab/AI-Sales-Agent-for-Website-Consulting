"""
Digital Gap Analysis Agent (Track B)

For no-website businesses: produces a structured gap analysis comparing
their digital presence against local competitors, then scores the opportunity.
"""

import json
import anthropic
from rich.console import Console
from config import settings
from models.business import Business
from models.analysis import DigitalGapAnalysis

console = Console()

CORE_DIRECTORIES = ["yelp", "yellowpages", "bbb", "angi", "homeadvisor", "thumbtack", "nextdoor"]


class DigitalGapAnalysisAgent:

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def analyze(self, business: Business, competitor_snapshot: dict | None = None) -> DigitalGapAnalysis:
        """Produces a digital gap analysis for a no-website business."""
        signals = self._extract_signals(business)
        analysis = await self._ai_score(business, signals, competitor_snapshot or {})
        console.log(
            f"[yellow]No-website score[/yellow] {business.name}: {analysis.no_website_score}/100"
        )
        return analysis

    def _extract_signals(self, business: Business) -> dict:
        has_gbp = business.google_review_count is not None and business.google_review_count > 0

        directories_present = set(business.in_other_directories)
        directories_missing = [d for d in CORE_DIRECTORIES if d not in directories_present]

        gbp_missing_fields = []
        if not business.google_profile_complete:
            gbp_missing_fields = ["hours", "description", "photos", "Q&A responses"]

        return {
            "has_google_profile": has_gbp,
            "google_profile_complete": business.google_profile_complete,
            "google_rating": business.google_rating,
            "google_review_count": business.google_review_count or 0,
            "yelp_present": bool(business.yelp_url),
            "directories_present": list(directories_present),
            "directories_missing": directories_missing,
            "citation_count": len(directories_present) + (1 if has_gbp else 0),
            "nap_consistent": True,  # would require deeper NAP audit tool
            "missing_gbp_fields": gbp_missing_fields,
        }

    async def _ai_score(
        self, business: Business, signals: dict, competitor_snapshot: dict
    ) -> DigitalGapAnalysis:
        prompt = f"""You are a local SEO and digital presence auditor evaluating a business that has NO website.

Business: {business.name} ({business.industry}) — {business.location}
Phone: {business.phone or 'unknown'}

Digital presence signals:
{json.dumps(signals, indent=2)}

Competitor context (if available):
{json.dumps(competitor_snapshot, indent=2) if competitor_snapshot else "No competitor data available — assume typical Charlotte market where 70% of competitors have websites."}

Return a JSON object with these exact keys:
{{
  "no_website_score": <integer 0-100, higher = bigger opportunity for us>,
  "summary": "<2-3 sentence plain-English gap summary>",
  "visibility_gaps": ["<gap 1>", "<gap 2>", "<gap 3>"],
  "fast_capture_recommendations": ["<rec 1>", "<rec 2>", "<rec 3>"],
  "local_competitors_with_websites": <integer estimate>,
  "local_competitor_count": <integer estimate>,
  "estimated_monthly_missed_leads": <integer estimate>,
  "competitor_website_percentage": <float 0.0-1.0>,
  "google_profile_score": <integer 0-100>,
  "gbp_photo_count": <integer estimate>,
  "review_recency_days": <integer or null>
}}

No-website opportunity scoring (0–100):
- 80–100: High-intent industry, many local competitors with sites, minimal digital presence
- 60–79: Moderate gap — some presence but clearly missing leads
- 40–59: GBP is decent but missing website and key directories
- 20–39: Small gap — already well-covered in directories
- 0–19: Niche where web presence matters less (unusual)

Fast capture recommendations should be concrete: e.g. "one-page site with service list and click-to-call CTA" or "claim and optimize Google Business Profile with 10+ photos."
"""

        response = self.client.messages.create(
            model=settings.agent_model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            ai_data = json.loads(raw)
        except json.JSONDecodeError:
            ai_data = {}

        return DigitalGapAnalysis(
            has_google_profile=signals["has_google_profile"],
            google_profile_score=ai_data.get("google_profile_score", 0),
            missing_gbp_fields=signals["missing_gbp_fields"],
            gbp_photo_count=ai_data.get("gbp_photo_count", 0),
            gbp_posts_active=False,
            gbp_qa_answered=False,
            total_reviews=signals["google_review_count"],
            avg_rating=signals["google_rating"],
            review_recency_days=ai_data.get("review_recency_days"),
            citation_count=signals["citation_count"],
            nap_consistent=signals["nap_consistent"],
            directories_missing=signals["directories_missing"],
            local_competitors_with_websites=ai_data.get("local_competitors_with_websites", 0),
            local_competitor_count=ai_data.get("local_competitor_count", 0),
            estimated_monthly_missed_leads=ai_data.get("estimated_monthly_missed_leads", 0),
            competitor_website_percentage=ai_data.get("competitor_website_percentage", 0.7),
            summary=ai_data.get("summary", ""),
            visibility_gaps=ai_data.get("visibility_gaps", []),
            fast_capture_recommendations=ai_data.get("fast_capture_recommendations", []),
            no_website_score=ai_data.get("no_website_score", 60),
        )
