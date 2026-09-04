"""Application configuration.

Loads environment variables and provides the configuration used

by the FlowPilot application.

"""

from dataclasses import dataclass

import os

from dotenv import load_dotenv

# Load the local .env file before the Settings object reads environment variables.

# This keeps API credentials and environment-specific values outside the source code.

load_dotenv()

@dataclass
class Settings:
    """Store application and BMONI configuration in one place."""


    # These values control the application's general runtime configuration.

    environment: str = os.getenv("FLOWPILOT_ENV", "development")

    secret: str = os.getenv("FLOWPILOT_SECRET", "dev-only-change-me")

    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite+pysqlite:///flowpilot.db"
    )

    # These values configure communication with the BMONI API.

    bmoni_mode: str = os.getenv("BMONI_MODE", "mock")

    bmoni_base_url: str = os.getenv("BMONI_BASE_URL", "")

    bmoni_api_key: str = os.getenv("BMONI_API_KEY", "")

    bmoni_webhook_secret: str = os.getenv("BMONI_WEBHOOK_SECRET", "")

    # Authentication tokens remain valid for one hour by default.

    access_token_minutes: int = 60

    # Prevent individual transactions from exceeding ₦500,000.

    max_transaction_minor: int = 50_000_000

    # Currency Shield triggers when the observed currency movement reaches 5%.

    fx_alert_threshold_bps: int = 500

    # Currency Shield may convert no more than 25% of available pocket funds.

    max_fx_conversion_percent: int = 25

    auth_rate_limit_per_minute: int = int(
        os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "10")
    )

    financial_rate_limit_per_minute: int = int(
        os.getenv("FINANCIAL_RATE_LIMIT_PER_MINUTE", "30")
    )

# Create the shared settings instance used by the application.

settings = Settings()
