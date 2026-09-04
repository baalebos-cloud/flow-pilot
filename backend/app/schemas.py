from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
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


class CurrencyShieldRequest(BaseModel):
    pocket_id: str
    target_currency: str = "USD"
    amount_minor: int = Field(gt=0)
    observed_change_bps: int
    observation_window_days: int = Field(ge=1, le=365)


class FxQuoteRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    source_currency: str = "CNGN"
    target_currency: str = "USD"
