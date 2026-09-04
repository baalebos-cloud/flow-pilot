from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ActionType(str, Enum):
    MONEY_TRANSFER = "money_transfer"
    BANK_WITHDRAWAL = "bank_withdrawal"
    CURRENCY_EXCHANGE = "currency_exchange"
    CREATE_POCKET = "create_pocket"
    POCKET_TRANSFER = "pocket_transfer"
    SPENDING_ANALYSIS = "spending_analysis"
    INVESTMENT_DISCOVERY = "investment_discovery"
    CURRENCY_PROTECTION = "currency_protection"
    UNKNOWN = "unknown"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


EXECUTABLE_ACTIONS = {
    ActionType.MONEY_TRANSFER,
    ActionType.BANK_WITHDRAWAL,
    ActionType.CURRENCY_EXCHANGE,
    ActionType.CREATE_POCKET,
    ActionType.POCKET_TRANSFER,
    ActionType.CURRENCY_PROTECTION,
}

READ_ONLY_ACTIONS = {
    ActionType.SPENDING_ANALYSIS,
    ActionType.INVESTMENT_DISCOVERY,
}


class FinancialIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    amount: Optional[int] = Field(default=None, ge=1)
    currency: Optional[str] = None
    destination: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    reason: str = Field(min_length=1, max_length=500)
    requires_user_approval: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value):
        if value is None:
            return None

        value = value.strip().upper()

        currency_map = {
            "NAIRA": "NGN",
            "₦": "NGN",
            "NIGERIAN NAIRA": "NGN",
            "DOLLAR": "USD",
            "DOLLARS": "USD",
            "$": "USD",
            "EURO": "EUR",
            "EUROS": "EUR",
            "POUND": "GBP",
            "POUNDS": "GBP",
            "BRITISH POUND": "GBP",
            "CNGN": "CNGN",
        }

        return currency_map.get(value, value)

    @model_validator(mode="after")
    def validate_clarification(self):
        if self.needs_clarification and not self.clarification_question:
            raise ValueError(
                "clarification_question is required when "
                "needs_clarification is true"
            )

        return self