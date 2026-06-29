from pydantic import BaseModel


class WebsiteAnalysis(BaseModel):
    """Track A: analysis for businesses that have a website."""

    url: str

    # SEO signals
    has_title_tag: bool = False
    has_meta_description: bool = False
    has_h1: bool = False
    page_count_estimate: int = 0
    has_sitemap: bool = False
    has_schema_markup: bool = False
    indexed_pages_estimate: int = 0

    # UX / conversion signals
    mobile_friendly: bool = False
    has_contact_form: bool = False
    has_phone_cta: bool = False
    has_google_maps_embed: bool = False
    has_ssl: bool = False
    has_clear_services_page: bool = False

    # Performance signals
    load_time_seconds: float | None = None
    image_count: int = 0
    has_lazy_loading: bool = False

    # Content signals
    has_about_page: bool = False
    has_testimonials: bool = False
    blog_post_count: int = 0
    last_updated_estimate: str | None = None

    # Staleness signals
    copyright_year: int | None = None          # year found in footer copyright
    is_stale: bool = False                     # True if site appears outdated
    staleness_reasons: list[str] = []          # human-readable reasons
    uses_outdated_tech: bool = False           # Flash, old jQuery, etc.
    has_mobile_viewport: bool = False          # <meta name="viewport">

    # Narrative (heuristic or AI-generated)
    summary: str = ""
    top_issues: list[str] = []
    quick_wins: list[str] = []

    # Score 0–100
    website_score: int = 0

    @property
    def age_label(self) -> str:
        if not self.copyright_year:
            return "Unknown age"
        import datetime
        age = datetime.datetime.now().year - self.copyright_year
        if age <= 1:
            return "Current"
        if age <= 3:
            return f"{age} years old"
        return f"{age}+ years old — likely outdated"


class DigitalGapAnalysis(BaseModel):
    """Track B: analysis for businesses without a website."""

    # Google Business Profile audit
    has_google_profile: bool = False
    google_profile_score: int = 0  # 0–100 based on completeness
    missing_gbp_fields: list[str] = []
    gbp_photo_count: int = 0
    gbp_posts_active: bool = False
    gbp_qa_answered: bool = False

    # Review landscape
    total_reviews: int = 0
    avg_rating: float | None = None
    review_recency_days: int | None = None  # days since last review
    competitor_avg_review_count: int = 0

    # Directory / citation audit
    citation_count: int = 0  # how many directories they appear in
    nap_consistent: bool = True  # Name / Address / Phone consistency
    directories_missing: list[str] = []

    # Competitor context
    local_competitors_with_websites: int = 0
    local_competitor_count: int = 0

    # Revenue impact estimate
    estimated_monthly_missed_leads: int = 0
    competitor_website_percentage: float = 0.0

    # AI narrative
    summary: str = ""
    visibility_gaps: list[str] = []
    fast_capture_recommendations: list[str] = []

    # Score 0–100 (higher = bigger opportunity)
    no_website_score: int = 0
