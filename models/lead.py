from enum import Enum
from datetime import datetime
from pydantic import BaseModel
from .business import Business
from .analysis import WebsiteAnalysis, DigitalGapAnalysis


class TrackType(str, Enum):
    WEBSITE_EXISTS = "website_exists"   # Track A: optimize existing site
    NO_WEBSITE = "no_website"           # Track B: greenfield capture


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OpportunityScore(BaseModel):
    track: TrackType
    raw_score: int        # 0–100
    final_score: int      # max(website_score, no_website_score)
    priority: Priority
    scoring_notes: list[str] = []


class EmailDraft(BaseModel):
    subject: str
    body: str
    track: TrackType
    personalization_tokens: dict[str, str] = {}


class Lead(BaseModel):
    business: Business
    track: TrackType
    website_analysis: WebsiteAnalysis | None = None
    digital_gap_analysis: DigitalGapAnalysis | None = None
    opportunity_score: OpportunityScore | None = None
    email_draft: EmailDraft | None = None
    created_at: datetime = datetime.now()
    status: str = "pending_review"

    @property
    def is_high_priority(self) -> bool:
        return (
            self.opportunity_score is not None
            and self.opportunity_score.priority == Priority.HIGH
        )
