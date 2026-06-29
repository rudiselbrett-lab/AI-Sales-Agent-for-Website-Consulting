"""
Pipeline Orchestrator

Runs the full two-track SMB discovery pipeline for a batch of businesses:

  Business Prospecting Agent
        │
        ▼
  Website Router ──────────────────────┐
        │                              │
   Track A                        Track B
  (has website)               (no website)
        │                              │
  Website Crawl            Presence Reconstruction
        │                              │
  Website Analysis          Digital Gap Analysis
        │                              │
        └──────────┬───────────────────┘
                   ▼
         Opportunity Scoring Engine
                   │
         (filter: score ≥ threshold)
                   │
         Contact Discovery Agent
                   │
         Personalization Agent
                   │
         Email Draft Agent
                   │
         Review Queue (JSONL)
"""

import asyncio
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from config import settings
from models.business import Business
from models.lead import Lead, TrackType
from agents import (
    ProspectingAgent,
    WebsiteRouter,
    WebsiteCrawlAgent,
    PresenceReconstructionAgent,
    WebsiteAnalysisAgent,
    DigitalGapAnalysisAgent,
    OpportunityScoringEngine,
    ContactDiscoveryAgent,
    PersonalizationAgent,
    EmailDraftAgent,
)
from .review_queue import ReviewQueue

console = Console()


class PipelineOrchestrator:

    def __init__(self):
        self.prospector = ProspectingAgent()
        self.router = WebsiteRouter()
        self.crawler = WebsiteCrawlAgent()
        self.presence_agent = PresenceReconstructionAgent()
        self.website_analyzer = WebsiteAnalysisAgent()
        self.gap_analyzer = DigitalGapAnalysisAgent()
        self.scorer = OpportunityScoringEngine()
        self.contact_agent = ContactDiscoveryAgent()
        self.personalizer = PersonalizationAgent()
        self.emailer = EmailDraftAgent()
        self.review_queue = ReviewQueue(settings.review_queue_path)

    async def run(
        self,
        industries: list[str] | None = None,
        total_limit: int = 5,
    ) -> list[Lead]:
        industries = industries or settings.industry_list
        # Distribute the total limit evenly across industries
        per_industry = max(1, -(-total_limit // len(industries)))  # ceiling divide

        all_leads: list[Lead] = []

        console.rule("[bold blue]SMB Discovery Pipeline — Charlotte, NC")

        for industry in industries:
            if len(all_leads) >= total_limit:
                break
            console.rule(f"[cyan]{industry.upper()}")
            businesses = await self.prospector.discover(industry, limit=per_industry)
            console.log(f"Found {len(businesses)} businesses")

            tasks = [self._process_business(b) for b in businesses]
            leads = await asyncio.gather(*tasks, return_exceptions=True)

            for result in leads:
                if isinstance(result, Exception):
                    console.log(f"[red]Error:[/red] {result}")
                elif result is not None:
                    all_leads.append(result)

        high_priority = [l for l in all_leads if l.is_high_priority]
        console.rule("[bold green]Pipeline Complete")
        console.log(
            f"Total leads: {len(all_leads)} | "
            f"High priority: {len(high_priority)} | "
            f"Queued for review: {len([l for l in all_leads if l.email_draft])}"
        )

        return all_leads

    async def _process_business(self, business: Business) -> Lead | None:
        try:
            # Step 1: Route to track A or B
            track, business = await self.router.route(business)

            # Step 2a: Track A — website exists
            if track == TrackType.WEBSITE_EXISTS:
                crawl = await self.crawler.crawl(business)
                if not crawl or not crawl.pages:
                    # Couldn't crawl — demote to Track B
                    track = TrackType.NO_WEBSITE
                    website_analysis = None
                    business = business.model_copy(update={"website_url": None})
                    business = await self.presence_agent.reconstruct(business)
                    digital_gap_analysis = await self.gap_analyzer.analyze(business)
                else:
                    website_analysis = await self.website_analyzer.analyze(business, crawl)
                    digital_gap_analysis = None

            # Step 2b: Track B — no website
            else:
                business = await self.presence_agent.reconstruct(business)
                digital_gap_analysis = await self.gap_analyzer.analyze(business)
                website_analysis = None

            # Step 3: Score the opportunity
            score = self.scorer.score(
                track=track,
                website_analysis=website_analysis,
                digital_gap_analysis=digital_gap_analysis,
            )

            # Filter below threshold
            if score.final_score < settings.min_opportunity_score:
                return None

            # Step 4: Contact discovery
            business = await self.contact_agent.discover(business)

            # Step 5: Personalize
            tokens = self.personalizer.build_tokens(
                business=business,
                track=track,
                website_analysis=website_analysis,
                digital_gap_analysis=digital_gap_analysis,
            )

            # Step 6: Draft email
            email_draft = await self.emailer.draft(track=track, tokens=tokens)

            lead = Lead(
                business=business,
                track=track,
                website_analysis=website_analysis,
                digital_gap_analysis=digital_gap_analysis,
                opportunity_score=score,
                email_draft=email_draft,
            )

            # Step 7: Add to review queue
            self.review_queue.enqueue(lead)
            return lead

        except Exception as exc:
            console.log(f"[red]Failed to process {business.name}:[/red] {exc}")
            raise
