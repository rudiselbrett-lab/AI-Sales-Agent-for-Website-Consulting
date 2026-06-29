"""
Opportunity Scoring Engine

Two scoring modes:
  A. Website Present Score (0–100) — quality/conversion gaps
  B. No-Website Score (0–100) — visibility/capture opportunity

Final score = max(website_score, no_website_score)
Priority tiers: HIGH ≥ 70, MEDIUM 40–69, LOW < 40
"""

from rich.console import Console
from models.lead import TrackType, OpportunityScore, Priority
from models.analysis import WebsiteAnalysis, DigitalGapAnalysis

console = Console()

HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40


class OpportunityScoringEngine:

    def score(
        self,
        track: TrackType,
        website_analysis: WebsiteAnalysis | None = None,
        digital_gap_analysis: DigitalGapAnalysis | None = None,
    ) -> OpportunityScore:
        notes: list[str] = []

        if track == TrackType.WEBSITE_EXISTS and website_analysis:
            raw = website_analysis.website_score
            notes = self._website_notes(website_analysis)
        elif track == TrackType.NO_WEBSITE and digital_gap_analysis:
            raw = digital_gap_analysis.no_website_score
            notes = self._no_website_notes(digital_gap_analysis)
        else:
            raw = 50
            notes = ["Insufficient data for scoring"]

        final = raw
        priority = self._priority(final)

        console.log(
            f"[bold]Score:[/bold] {final}/100 → [{self._priority_color(priority)}]{priority}[/{self._priority_color(priority)}]"
        )

        return OpportunityScore(
            track=track,
            raw_score=raw,
            final_score=final,
            priority=priority,
            scoring_notes=notes,
        )

    def _website_notes(self, a: WebsiteAnalysis) -> list[str]:
        notes = []
        if not a.mobile_friendly:
            notes.append("Not mobile-friendly — major conversion leak")
        if not a.has_contact_form and not a.has_phone_cta:
            notes.append("No clear contact CTA")
        if not a.has_ssl:
            notes.append("No HTTPS — trust issue")
        if a.load_time_seconds and a.load_time_seconds > 3:
            notes.append(f"Slow load time: {a.load_time_seconds}s")
        if not a.has_clear_services_page:
            notes.append("No dedicated services page")
        return notes

    def _no_website_notes(self, a: DigitalGapAnalysis) -> list[str]:
        notes = []
        pct = int(a.competitor_website_percentage * 100)
        if pct > 0:
            notes.append(f"{pct}% of local competitors have websites")
        if a.estimated_monthly_missed_leads > 0:
            notes.append(f"Est. {a.estimated_monthly_missed_leads} missed inbound leads/month")
        if not a.has_google_profile:
            notes.append("No Google Business Profile detected")
        if a.directories_missing:
            notes.append(f"Missing from: {', '.join(a.directories_missing[:3])}")
        return notes

    def _priority(self, score: int) -> Priority:
        if score >= HIGH_THRESHOLD:
            return Priority.HIGH
        if score >= MEDIUM_THRESHOLD:
            return Priority.MEDIUM
        return Priority.LOW

    def _priority_color(self, priority: Priority) -> str:
        return {"high": "red", "medium": "yellow", "low": "dim"}.get(priority.value, "white")
