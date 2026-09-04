from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


ReferenceId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]

CurrencyCode = Annotated[
    str,
    Field(
        min_length=3,
        max_length=10,
        pattern=r"^[A-Z0-9]+$",
    ),
]

BasisPoints = Annotated[
    int,
    Field(ge=-100_000, le=100_000),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class RecommendationType(StrEnum):
    TRANSFER = "TRANSFER"
    BANK_WITHDRAWAL = "BANK_WITHDRAWAL"
    POCKET_CREATION = "POCKET_CREATION"
    POCKET_TRANSFER = "POCKET_TRANSFER"
    CURRENCY_PROTECTION = "CURRENCY_PROTECTION"
    SPENDING_ANALYSIS = "SPENDING_ANALYSIS"
    INVESTMENT_DISCOVERY = "INVESTMENT_DISCOVERY"


class IntentReasonCode(StrEnum):
    USER_REQUESTED_TRANSFER = "USER_REQUESTED_TRANSFER"
    USER_REQUESTED_WITHDRAWAL = "USER_REQUESTED_WITHDRAWAL"
    USER_REQUESTED_POCKET_CREATION = "USER_REQUESTED_POCKET_CREATION"
    USER_REQUESTED_POCKET_TRANSFER = "USER_REQUESTED_POCKET_TRANSFER"
    USER_REQUESTED_CURRENCY_PROTECTION = "USER_REQUESTED_CURRENCY_PROTECTION"
    USER_REQUESTED_SPENDING_ANALYSIS = "USER_REQUESTED_SPENDING_ANALYSIS"
    USER_REQUESTED_INVESTMENT_DISCOVERY = "USER_REQUESTED_INVESTMENT_DISCOVERY"


class EvidenceReasonCode(StrEnum):
    CURRENCY_DECLINE_THRESHOLD_REACHED = "CURRENCY_DECLINE_THRESHOLD_REACHED"
    DISCRETIONARY_FUNDS_AVAILABLE = "DISCRETIONARY_FUNDS_AVAILABLE"
    SPENDING_LIMIT_AT_RISK = "SPENDING_LIMIT_AT_RISK"
    UNUSUAL_SPENDING_DETECTED = "UNUSUAL_SPENDING_DETECTED"
    POCKET_UNDERFUNDED = "POCKET_UNDERFUNDED"
    SAVINGS_TARGET_BEHIND = "SAVINGS_TARGET_BEHIND"
    VERIFIED_OPPORTUNITY_MATCH = "VERIFIED_OPPORTUNITY_MATCH"


ReasonCode = IntentReasonCode | EvidenceReasonCode


class ClarificationReasonCode(StrEnum):
    MISSING_AMOUNT = "MISSING_AMOUNT"
    MISSING_CURRENCY = "MISSING_CURRENCY"
    MISSING_DESTINATION = "MISSING_DESTINATION"
    AMBIGUOUS_INTENT = "AMBIGUOUS_INTENT"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class PocketPurpose(StrEnum):
    FOOD = "FOOD"
    TRANSPORT = "TRANSPORT"
    RENT = "RENT"
    EMERGENCY = "EMERGENCY"
    SAVINGS = "SAVINGS"
    INVESTMENT = "INVESTMENT"
    DISCRETIONARY = "DISCRETIONARY"
    OTHER = "OTHER"


class RecipientType(StrEnum):
    SAVED_BANK = "SAVED_BANK"
    SAVED_WALLET = "SAVED_WALLET"


class PocketContext(StrictModel):
    reference_id: ReferenceId
    purpose: PocketPurpose
    currency: CurrencyCode
    available_minor: int = Field(ge=0)
    protected: bool


class MarketObservation(StrictModel):
    reference_id: ReferenceId
    source: str = Field(min_length=2, max_length=120)
    source_currency: CurrencyCode
    target_currency: CurrencyCode
    change_bps: BasisPoints
    window_days: int = Field(ge=1, le=365)
    observed_at: datetime


class InvestmentOpportunity(StrictModel):
    reference_id: ReferenceId
    provider_name: str = Field(min_length=2, max_length=120)
    regulator: str = Field(min_length=2, max_length=120)
    registration_reference: str = Field(min_length=2, max_length=120)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    liquidity: str = Field(min_length=2, max_length=200)
    fee_summary: str = Field(min_length=2, max_length=300)
    minimum_amount_minor: int = Field(ge=0)
    currency: CurrencyCode
    verified_at: datetime


class RecipientContext(StrictModel):
    reference_id: ReferenceId
    type: RecipientType
    display_name: str = Field(min_length=2, max_length=120)
    currency: CurrencyCode


class RecommendationContext(StrictModel):
    base_currency: CurrencyCode
    pockets: list[PocketContext] = Field(
        default_factory=list,
        max_length=50,
    )
    market_observations: list[MarketObservation] = Field(
        default_factory=list,
        max_length=20,
    )
    investment_opportunities: list[InvestmentOpportunity] = Field(
        default_factory=list,
        max_length=20,
    )
    recipients: list[RecipientContext] = Field(
        default_factory=list,
        max_length=20,
    )
    allowed_recommendation_types: set[RecommendationType] = Field(
        min_length=1
    )


class RecommendationRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: ReferenceId
    user_message: str = Field(
        min_length=1,
        max_length=1_000,
    )
    context: RecommendationContext


class TransferParameters(StrictModel):
    kind: Literal[RecommendationType.TRANSFER]
    amount_minor: int = Field(gt=0)
    currency: CurrencyCode
    recipient_reference_id: ReferenceId


class BankWithdrawalParameters(StrictModel):
    kind: Literal[RecommendationType.BANK_WITHDRAWAL]
    amount_minor: int = Field(gt=0)
    currency: CurrencyCode
    recipient_reference_id: ReferenceId


class PocketCreationParameters(StrictModel):
    kind: Literal[RecommendationType.POCKET_CREATION]
    suggested_name: str = Field(
        min_length=2,
        max_length=60,
    )
    purpose: PocketPurpose
    amount_minor: int = Field(ge=0)
    currency: CurrencyCode
    protected: bool


class PocketTransferParameters(StrictModel):
    kind: Literal[RecommendationType.POCKET_TRANSFER]
    source_pocket_reference_id: ReferenceId
    target_pocket_reference_id: ReferenceId
    amount_minor: int = Field(gt=0)
    currency: CurrencyCode


class CurrencyProtectionParameters(StrictModel):
    kind: Literal[RecommendationType.CURRENCY_PROTECTION]
    pocket_reference_id: ReferenceId
    market_observation_reference_id: ReferenceId
    suggested_amount_minor: int = Field(gt=0)
    source_currency: CurrencyCode
    target_currency: CurrencyCode


class SpendingAnalysisParameters(StrictModel):
    kind: Literal[RecommendationType.SPENDING_ANALYSIS]
    pocket_reference_ids: list[ReferenceId] = Field(
        default_factory=list,
        max_length=50,
    )
    window_days: int = Field(
        ge=1,
        le=365,
    )


class InvestmentDiscoveryParameters(StrictModel):
    kind: Literal[RecommendationType.INVESTMENT_DISCOVERY]
    pocket_reference_id: ReferenceId
    opportunity_reference_id: ReferenceId
    suggested_amount_minor: int = Field(gt=0)
    currency: CurrencyCode


RecommendationParameters = Annotated[
    TransferParameters
    | BankWithdrawalParameters
    | PocketCreationParameters
    | PocketTransferParameters
    | CurrencyProtectionParameters
    | SpendingAnalysisParameters
    | InvestmentDiscoveryParameters,
    Field(discriminator="kind"),
]


class ModelMetadata(StrictModel):
    provider: str = Field(
        min_length=1,
        max_length=80,
    )
    model: str = Field(
        min_length=1,
        max_length=120,
    )
    prompt_version: str = Field(
        min_length=1,
        max_length=40,
    )


class RecommendationResult(StrictModel):
    outcome: Literal["RECOMMENDATION"]
    schema_version: Literal["1.0"] = "1.0"
    request_id: ReferenceId
    recommendation_type: RecommendationType
    parameters: RecommendationParameters
    reason_codes: list[ReasonCode] = Field(
        min_length=1,
        max_length=10,
    )
    evidence_reference_ids: list[ReferenceId] = Field(
        default_factory=list,
        max_length=20,
    )
    confidence_bps: int = Field(
        ge=0,
        le=10_000,
    )
    explanation: str = Field(
        min_length=1,
        max_length=800,
    )
    requires_user_approval: bool
    model_metadata: ModelMetadata


class ClarificationRequired(StrictModel):
    outcome: Literal["CLARIFICATION_REQUIRED"]
    schema_version: Literal["1.0"] = "1.0"
    request_id: ReferenceId
    reason_code: ClarificationReasonCode
    question: str = Field(
        min_length=1,
        max_length=300,
    )
    model_metadata: ModelMetadata


class UnsupportedRequest(StrictModel):
    outcome: Literal["UNSUPPORTED"]
    schema_version: Literal["1.0"] = "1.0"
    request_id: ReferenceId
    reason: str = Field(
        min_length=1,
        max_length=300,
    )
    model_metadata: ModelMetadata


class ModelFailure(StrictModel):
    outcome: Literal["MODEL_ERROR"]
    schema_version: Literal["1.0"] = "1.0"
    request_id: ReferenceId
    error_code: Literal[
        "TIMEOUT",
        "INVALID_OUTPUT",
        "PROVIDER_UNAVAILABLE",
        "INTERNAL_ERROR",
    ]
    retryable: bool


OutcomeValue = Annotated[
    RecommendationResult
    | ClarificationRequired
    | UnsupportedRequest
    | ModelFailure,
    Field(discriminator="outcome"),
]


class RecommendationOutcome(RootModel[OutcomeValue]):
    pass
