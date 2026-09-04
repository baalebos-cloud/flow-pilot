import pytest

from app.balances import (
    available_balance_minor,
    decimal_to_minor,
    fetch_wallet_balances,
    minor_to_decimal,
)
from app.bmoni import BmoniError


class BalanceGateway:
    def __init__(self, response):
        self.response = response

    def get_wallet_balances(self, *, bmoni_user_id: str):
        assert bmoni_user_id == "user-1"
        return self.response


def test_decimal_balance_is_converted_without_float_rounding():
    assert decimal_to_minor("123.450000", "NGN") == 12_345
    assert decimal_to_minor("0.019999", "USD") == 1
    assert minor_to_decimal(100_000, "NGN") == "1000.00"


def test_balance_response_is_normalized_to_minor_units():
    gateway = BalanceGateway(
        {
            "data": {
                "balances": [
                    {
                        "smartWalletId": "wallet-1",
                        "currency": "NGN",
                        "balance": "250000.50",
                        "error": None,
                    }
                ]
            }
        }
    )

    result = fetch_wallet_balances(gateway, bmoni_user_id="user-1")

    assert result[0].currency == "CNGN"
    assert result[0].available_minor == 25_000_050
    assert available_balance_minor(
        gateway, bmoni_user_id="user-1", currency="CNGN"
    ) == 25_000_050


def test_per_currency_upstream_failure_is_not_treated_as_zero():
    gateway = BalanceGateway(
        {
            "data": {
                "balances": [
                    {
                        "smartWalletId": "wallet-1",
                        "currency": "NGN",
                        "balance": None,
                        "error": "RPC unavailable",
                    }
                ]
            }
        }
    )

    balance = fetch_wallet_balances(gateway, bmoni_user_id="user-1")[0]
    assert balance.available is False
    assert balance.available_minor is None

    with pytest.raises(BmoniError) as exc_info:
        available_balance_minor(gateway, bmoni_user_id="user-1", currency="CNGN")

    assert exc_info.value.code == "BMONI_BALANCE_UNAVAILABLE"
    assert exc_info.value.retryable is True


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "not-money"])
def test_invalid_vendor_balance_fails_closed(value):
    with pytest.raises(BmoniError):
        decimal_to_minor(value, "NGN")
