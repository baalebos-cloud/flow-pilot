from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Validate the information required to create a FlowPilot user."""

    email: EmailStr

    first_name: str = Field(min_length=2, max_length=60)

    last_name: str = Field(min_length=2, max_length=60)

    password: str = Field(min_length=8, max_length=128)

    phone_number: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class LoginRequest(BaseModel):
    email: EmailStr

    password: str


class WalletLinkRequest(BaseModel):
    wallet_address: str = Field(min_length=10, max_length=128)

    currency: str = "CNGN"


class OwnerProofChallengeRequest(BaseModel):
    owner_address: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")

    currency: str = "CNGN"


class ManagedWalletCreateRequest(OwnerProofChallengeRequest):
    challenge_id: str = Field(min_length=1, max_length=200)

    signature: str = Field(pattern=r"^0x[a-fA-F0-9]{130}$")


class ActionPlanRequest(BaseModel):
    message: str = Field(min_length=5, max_length=1000)

    amount_minor: int = Field(gt=0)

    currency: str = "CNGN"

    recipient_name: str = Field(min_length=2, max_length=120)

    available_balance_minor: int = Field(gt=0)


class SignatureRequest(BaseModel):
    signature: str = Field(min_length=10, max_length=1024)


class PocketCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)

    purpose: str = Field(min_length=2, max_length=120)

    allocated_minor: int = Field(ge=0)

    currency: str = "CNGN"

    protected: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Emergency Fund",
                "purpose": "Emergency savings",
                "allocated_minor": 5_000_000,
                "currency": "CNGN",
                "protected": True,
            }
        }
    }


# Validate the information required to transfer allocated funds between pockets.
class PocketTransferRequest(BaseModel):
    """Validate a transfer between two pockets owned by the same user."""

    source_pocket_id: str

    destination_pocket_id: str

    amount_minor: int = Field(gt=0)

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_pocket_id": "pocket_emergency",
                "destination_pocket_id": "pocket_rent",
                "amount_minor": 1_000_000,
            }
        }
    }


# Validate a transaction category supplied by the authenticated user.
class TransactionCategorizeRequest(BaseModel):
    """Validate the category assigned to a transaction."""

    category: str = Field(min_length=2, max_length=60)


class CurrencyShieldRequest(BaseModel):
    pocket_id: str

    target_currency: str = "USD"

    amount_minor: int = Field(gt=0)

    observed_change_bps: int

    observation_window_days: int = Field(ge=1, le=365)

    model_config = {
        "json_schema_extra": {
            "example": {
                "pocket_id": "pocket_travel",
                "target_currency": "USD",
                "amount_minor": 1_000_000,
                "observed_change_bps": -600,
                "observation_window_days": 30,
            }
        }
    }


# Represent a verified investment opportunity exposed as read-only information.
class InvestmentOpportunityResponse(BaseModel):
    """Describe an investment opportunity without providing execution controls."""

    id: str

    name: str

    provider: str

    regulatory_status: str

    risk_level: str

    liquidity: str

    fee_minor: int

    currency: str

    description: str

    verified_at: str


class FxQuoteRequest(BaseModel):
    amount_minor: int = Field(gt=0)

    source_currency: str = "CNGN"

    target_currency: str = "USD"


class ProposalSignatureRequest(BaseModel):
    signature: str = Field(pattern=r"^0x[a-fA-F0-9]{130}$")
