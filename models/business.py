from enum import Enum
from pydantic import BaseModel, HttpUrl


class WebsiteStatus(str, Enum):
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    BROKEN = "broken"  # domain exists but returns errors


class Business(BaseModel):
    name: str
    industry: str
    city: str
    state: str
    phone: str | None = None
    address: str | None = None

    # Source
    google_maps_url: str | None = None  # direct link back to the Maps listing

    # Website detection results
    website_url: str | None = None
    website_status: WebsiteStatus = WebsiteStatus.NOT_FOUND

    # Google Business Profile signals
    google_place_id: str | None = None
    google_rating: float | None = None
    google_review_count: int | None = None
    google_categories: list[str] = []
    google_profile_complete: bool = False

    # Directory presence
    yelp_url: str | None = None
    yelp_rating: float | None = None
    yelp_review_count: int | None = None
    in_other_directories: list[str] = []

    # Contact discovery
    owner_name: str | None = None
    owner_email: str | None = None
    contact_confidence: float = 0.0

    @property
    def has_website(self) -> bool:
        return self.website_status == WebsiteStatus.EXISTS

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def location(self) -> str:
        return f"{self.city}, {self.state}"
