from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = Field(default="")
    serpapi_key: str = Field(default="")
    hunter_api_key: str = Field(default="")
    clearbit_api_key: str = Field(default="")

    target_city: str = "Charlotte"
    target_state: str = "NC"
    target_industries: str = "plumber,electrician,hvac,roofer,landscaper,auto-repair,dentist,chiropractor,restaurant,salon"

    lead_batch_size: int = 25
    min_opportunity_score: int = 40
    review_queue_path: str = "./data/review_queue.jsonl"

    # Claude model for agent reasoning
    agent_model: str = "claude-sonnet-4-6"

    @property
    def industry_list(self) -> list[str]:
        return [i.strip() for i in self.target_industries.split(",")]


settings = Settings()
