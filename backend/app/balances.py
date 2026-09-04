from decimal import Decimal, InvalidOperation, ROUND_DOWN

from pydantic import BaseModel, ConfigDict

from app.bmoni import BmoniError, BmoniGateway


MINOR_UNITS = {
    "CAD": 2,
    "CNGN": 2,
    "EUR": 2,
    "GBP": 2,
    "MXN": 2,
    "NGN": 2,
    "USD": 2,
}

CURRENCY_ALIASES = {"NGN": "CNGN"}


class WalletBalance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bmoni_wallet_id: str
    currency: str
    available_minor: int | None
    available_display: str | None
    available: bool
    error: str | None = None


def decimal_to_minor(value: str, currency: str) -> int:
    places = MINOR_UNITS.get(currency)
    if places is None:
        raise BmoniError(
            f"Unsupported balance currency: {currency}",
            code="BMONI_UNSUPPORTED_CURRENCY",
            status_code=422,
        )
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise BmoniError(
            "BMONI returned an invalid balance", code="BMONI_INVALID_RESPONSE"
        ) from exc
    if not amount.is_finite() or amount < 0:
        raise BmoniError(
            "BMONI returned an invalid balance", code="BMONI_INVALID_RESPONSE"
        )
    scale = Decimal(10) ** places
    return int((amount * scale).to_integral_value(rounding=ROUND_DOWN))


def minor_to_decimal(value: int, currency: str) -> str:
    places = MINOR_UNITS.get(currency)
    if places is None or value <= 0:
        raise ValueError("Amount and currency cannot be converted to minor units")
    amount = Decimal(value) / (Decimal(10) ** places)
    return f"{amount:.{places}f}"


def fetch_wallet_balances(
    gateway: BmoniGateway, *, bmoni_user_id: str
) -> list[WalletBalance]:
    response = gateway.get_wallet_balances(bmoni_user_id=bmoni_user_id)
    entries = response.get("data", {}).get("balances")
    if not isinstance(entries, list):
        raise BmoniError(
            "BMONI balance response is invalid", code="BMONI_INVALID_RESPONSE"
        )
    balances = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("smartWalletId") or not entry.get("currency"):
            raise BmoniError(
                "BMONI balance entry is invalid", code="BMONI_INVALID_RESPONSE"
            )
        vendor_currency = str(entry["currency"]).upper()
        currency = CURRENCY_ALIASES.get(vendor_currency, vendor_currency)
        raw_balance = entry.get("balance")
        error = str(entry["error"]) if entry.get("error") else None
        available = raw_balance is not None and error is None
        balances.append(
            WalletBalance(
                bmoni_wallet_id=str(entry["smartWalletId"]),
                currency=currency,
                available_minor=(
                    decimal_to_minor(str(raw_balance), vendor_currency)
                    if available
                    else None
                ),
                available_display=str(raw_balance) if available else None,
                available=available,
                error=error,
            )
        )
    return balances


def available_balance_minor(
    gateway: BmoniGateway, *, bmoni_user_id: str, currency: str
) -> int:
    requested = currency.upper()
    for balance in fetch_wallet_balances(gateway, bmoni_user_id=bmoni_user_id):
        if balance.currency == requested:
            if not balance.available or balance.available_minor is None:
                raise BmoniError(
                    "Wallet balance is temporarily unavailable",
                    code="BMONI_BALANCE_UNAVAILABLE",
                    status_code=503,
                    retryable=True,
                )
            return balance.available_minor
    raise BmoniError(
        f"No BMONI wallet balance found for {requested}",
        code="BMONI_BALANCE_NOT_FOUND",
        status_code=404,
    )
