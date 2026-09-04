from dataclasses import dataclass
import os


@dataclass
class Settings:
    environment: str = os.getenv("FLOWPILOT_ENV", "development")
    secret: str = os.getenv("FLOWPILOT_SECRET", "dev-only-change-me")
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite+pysqlite:///flowpilot.db"
    )
    bmoni_mode: str = os.getenv("BMONI_MODE", "mock")
    bmoni_base_url: str = os.getenv("BMONI_BASE_URL", "")
    bmoni_api_key: str = os.getenv("BMONI_API_KEY", "")
    bmoni_webhook_secret: str = os.getenv("BMONI_WEBHOOK_SECRET", "")
    access_token_minutes: int = 60
    max_transaction_minor: int = 50_000_000  # NGN 500,000.00
    fx_alert_threshold_bps: int = 500
    max_fx_conversion_percent: int = 25
    auth_rate_limit_per_minute: int = int(
        os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "10")
    )
    financial_rate_limit_per_minute: int = int(
        os.getenv("FINANCIAL_RATE_LIMIT_PER_MINUTE", "30")
    )


settings = Settings()
