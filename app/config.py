from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql://contractor_ops:contractor_ops_dev@localhost:5432/contractor_ops"
    )
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    algorithm: str = "HS256"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
