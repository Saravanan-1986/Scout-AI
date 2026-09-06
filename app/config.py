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
    max_iterations: int = 3          # planner rounds (2 re-plans allowed)
    min_results: int = 8             # minimum relevant opportunities to aim for
    max_results: int = 10            # maximum opportunities shown to the user
    max_queries_per_round: int = 4   # search queries generated per planner round
    max_pages_per_round: int = 20    # webpages scraped per researcher round
    max_pages_per_source: int = 8    # detail pages discovered per whitelisted site
    max_search_results: int = 8      # results kept per search query
    search_delay_seconds: float = 0.3

    # --- Performance ---
    scrape_workers: int = 8          # concurrent page scrapes (thread pool)
    llm_explain_top: int = 5         # LLM explanations only for the top N ranked
    cache_hours: int = 24            # MongoDB opportunity-cache freshness window

    # --- Networking ---
    request_timeout: int = 10

    app_env: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

