from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql://contractor_ops:contractor_ops_dev@localhost:5432/contractor_ops"
    )
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    algorithm: str = "HS256"
    research_user_agent: str = "contractor-ops-ai/0.1 (+public-record-research-agent; contact:ops@example.com)"
    openai_api_key: str | None = None
    openai_research_model: str = "gpt-4.1-mini"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def sqlalchemy_database_url(self) -> str:
        """Normalize provider URLs so SQLAlchemy can always consume them."""
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql://", 1)
        return self.database_url


settings = Settings()
