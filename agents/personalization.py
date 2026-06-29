"""
Personalization Agent

Builds a token dict used by the Email Draft Agent.
Different tokens are populated depending on track (A vs B).
"""

from models.business import Business
from models.lead import TrackType
from models.analysis import WebsiteAnalysis, DigitalGapAnalysis


class PersonalizationAgent:

    def build_tokens(
        self,
        business: Business,
        track: TrackType,
        website_analysis: WebsiteAnalysis | None = None,
        digital_gap_analysis: DigitalGapAnalysis | None = None,
    ) -> dict[str, str]:
        tokens: dict[str, str] = {
            "BusinessName": business.name,
            "OwnerName": business.owner_name or "there",
            "Industry": business.industry.title(),
            "City": business.city,
        }

        if track == TrackType.WEBSITE_EXISTS and website_analysis:
            tokens.update(self._website_tokens(website_analysis, business))
        elif track == TrackType.NO_WEBSITE and digital_gap_analysis:
            tokens.update(self._no_website_tokens(digital_gap_analysis, business))

        return tokens

    def _website_tokens(self, a: WebsiteAnalysis, business: Business) -> dict[str, str]:
        issues = a.top_issues[:2] if a.top_issues else ["site performance", "conversion elements"]
        wins = a.quick_wins[:2] if a.quick_wins else ["improved mobile layout", "clearer contact CTA"]

        return {
            "TopIssue1": issues[0] if issues else "site speed",
            "TopIssue2": issues[1] if len(issues) > 1 else "mobile UX",
            "QuickWin1": wins[0] if wins else "add a click-to-call button",
            "QuickWin2": wins[1] if len(wins) > 1 else "improve page load speed",
            "WebsiteUrl": business.website_url or "",
            "WebsiteScore": str(a.website_score),
        }

    def _no_website_tokens(self, a: DigitalGapAnalysis, business: Business) -> dict[str, str]:
        pct = int(a.competitor_website_percentage * 100)
        missed = a.estimated_monthly_missed_leads

        gaps = a.visibility_gaps[:2] if a.visibility_gaps else ["local search visibility", "inbound lead capture"]
        recs = a.fast_capture_recommendations[:1] if a.fast_capture_recommendations else ["a simple one-page website"]

        return {
            "CompetitorPct": str(pct),
            "MissedLeads": str(missed) if missed > 0 else "several",
            "VisibilityGap1": gaps[0] if gaps else "search visibility",
            "VisibilityGap2": gaps[1] if len(gaps) > 1 else "directory presence",
            "FastCapture": recs[0] if recs else "a simple one-page website with a quote form",
        }
