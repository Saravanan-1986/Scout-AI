from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Database (optional: results are saved when reachable) ---
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "scout_ai"

    # --- Providers (ALL optional; ScoutAI degrades gracefully without them) ---
    tavily_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    enable_llm: bool = True

    # --- Agent behaviour ---
    max_iterations: int = 2          # planner rounds (1 re-plan allowed)
    min_results: int = 5             # verified relevant opportunities needed before stopping
    max_queries_per_round: int = 4   # search queries generated per planner round
    max_pages_per_round: int = 10    # webpages scraped per researcher round
    max_pages_per_source: int = 4    # detail pages discovered per whitelisted site
    max_search_results: int = 5      # results kept per search query
    search_delay_seconds: float = 1.0

    # --- Networking ---
    request_timeout: int = 15

    app_env: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

