from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class WalletLinkRequest(BaseModel):
    wallet_address: str = Field(min_length=10, max_length=128)
    currency: str = "CNGN"


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
