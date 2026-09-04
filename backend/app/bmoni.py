"""BMONI boundary with a deterministic mock and a fail-closed HTTP client."""

import hashlib
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import settings


class BmoniError(RuntimeError):
    """Represent a controlled BMONI integration error."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int = 502,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class BmoniConfigurationError(BmoniError):
    """Raised when the BMONI integration is missing required configuration."""

    def __init__(self, message: str):
        super().__init__(
            message,
            code="BMONI_NOT_CONFIGURED",
            status_code=503,
        )


class BmoniConflictError(BmoniError):
    """Raised when BMONI reports a resource conflict."""

    pass


@dataclass
class BmoniGateway:
    """Provide the application with the operations it needs from BMONI."""

    mode: str = settings.bmoni_mode
    base_url: str = settings.bmoni_base_url
    api_key: str = settings.bmoni_api_key

    def _live_unconfigured(self, operation: str) -> None:
        """Raise a configuration error for unsupported live operations."""
        raise BmoniConfigurationError(
            f"BMONI operation '{operation}' is not configured for {self.mode} mode"
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request to BMONI and normalize vendor errors."""
        if self.mode not in {"sandbox", "live"}:
            self._live_unconfigured(f"{method} {path}")

        base_url = settings.bmoni_base_url.rstrip("/")

        if not base_url or not settings.bmoni_api_key:
            raise BmoniConfigurationError(
                "BMONI_BASE_URL and BMONI_API_KEY are required outside mock mode"
            )

        try:
            response = httpx.request(
                method,
                f"{base_url}{path}",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-api-key": settings.bmoni_api_key,
                },
                json=json_body,
                params=params,
                timeout=10.0,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise BmoniError(
                "BMONI is temporarily unreachable",
                code="BMONI_UNAVAILABLE",
                status_code=503,
                retryable=True,
            ) from exc

        if response.is_success:
            try:
                return response.json()
            except ValueError as exc:
                raise BmoniError(
                    "BMONI returned an invalid response",
                    code="BMONI_INVALID_RESPONSE",
                ) from exc

        message = "BMONI rejected the request"

        try:
            error_body = response.json()
            candidate = error_body.get("message")

            if isinstance(candidate, list):
                message = "; ".join(str(item) for item in candidate)
            elif candidate:
                message = str(candidate)
        except ValueError:
            pass

        if response.status_code == 409:
            raise BmoniConflictError(
                message,
                code="BMONI_CONFLICT",
                status_code=409,
            )

        mapped_status = 422 if response.status_code == 400 else 502

        if response.status_code in {401, 403}:
            mapped_status = 503

        raise BmoniError(
            message,
            code=f"BMONI_HTTP_{response.status_code}",
            status_code=mapped_status,
            retryable=response.status_code == 429
            or response.status_code >= 500,
        )

    def _find_user(
        self,
        *,
        external_id: str,
        email: str,
    ) -> dict[str, str] | None:
        """Find an existing BMONI user after a creation conflict."""
        page = 1

        while page <= 10:
            result = self._request(
                "GET",
                "/v1/users",
                params={
                    "page": page,
                    "limit": 100,
                },
            )

            users = result.get("users", []) if isinstance(result, dict) else []

            for user in users:
                identity_matches = user.get("identityId") == external_id

                email_matches = (
                    str(user.get("email", "")).lower() == email.lower()
                )

                if identity_matches or email_matches:
                    return {
                        "id": str(user["bmoniUserId"]),
                        "status": "ACTIVE",
                    }

            if len(users) < 100:
                break

            page += 1

        return None

    def create_user(
        self,
        *,
        external_id: str,
        email: str,
        first_name: str,
        last_name: str,
        phone_number: str,
    ) -> dict[str, str]:
        """Create the corresponding user in BMONI."""
        if self.mode == "mock":
            return {
                "id": f"bm_usr_{uuid.uuid4().hex[:16]}",
                "status": "ACTIVE",
            }

        try:
            result = self._request(
                "POST",
                "/v1/users",
                json_body={
                    "identityId": external_id,
                    "firstName": first_name,
                    "lastName": last_name,
                    "email": email,
                    "phoneNumber": phone_number,
                },
            )
        except BmoniConflictError:
            existing = self._find_user(
                external_id=external_id,
                email=email,
            )

            if existing:
                return existing

            raise

        try:
            return {
                "id": str(result["user"]["bmoniUserId"]),
                "status": "ACTIVE",
            }
        except (KeyError, TypeError) as exc:
            raise BmoniError(
                "BMONI user response is missing bmoniUserId",
                code="BMONI_INVALID_RESPONSE",
            ) from exc

    def link_wallet(
        self,
        *,
        bmoni_user_id: str,
        address: str,
        currency: str,
    ) -> dict:
        """Provide the wallet-linking operation used by the application."""
        if self.mode != "mock":
            self._live_unconfigured("owner-proof wallet provisioning")

        return {
            "id": f"bm_wal_{uuid.uuid4().hex[:16]}",
            "status": "ACTIVE",
        }

    def create_owner_proof_challenge(
        self,
        *,
        bmoni_user_id: str,
        owner_address: str,
        currency: str,
    ) -> dict:
        """Create an owner-proof challenge for managed-wallet provisioning."""
        if self.mode == "mock":
            return {
                "challengeId": f"challenge_{uuid.uuid4().hex}",
                "groupId": f"group_{uuid.uuid4().hex}",
                "message": f"FlowPilot owner proof for {owner_address}",
                "expiresAt": "2099-01-01T00:00:00.000Z",
            }

        return self._request(
            "POST",
            f"/v1/users/{bmoni_user_id}/smart-wallets/owner-proof-challenges",
            json_body={
                "currency": currency,
                "userOwnerAddress": owner_address,
            },
        )

    def list_wallets(
        self,
        *,
        bmoni_user_id: str,
    ) -> list[dict]:
        """List managed wallets belonging to a BMONI user."""
        result = self._request(
            "GET",
            f"/v1/users/{bmoni_user_id}/smart-wallets/account/wallets",
        )

        if not isinstance(result, list):
            raise BmoniError(
                "BMONI wallet response is invalid",
                code="BMONI_INVALID_RESPONSE",
            )

        return result

    def get_wallet_balances(
        self,
        *,
        bmoni_user_id: str,
    ) -> dict:
        """Return authoritative wallet balances from BMONI."""
        if self.mode == "mock":
            return {
                "data": {
                    "smartAccountAddress": None,
                    "balances": [
                        {
                            "smartWalletId": "mock-cngn-wallet",
                            "currency": "NGN",
                            "balance": "300000.00",
                            "error": None,
                        }
                    ],
                }
            }

        result = self._request(
            "GET",
            f"/v1/users/{bmoni_user_id}/smart-wallets/account/balances",
        )

        if not isinstance(result, dict):
            raise BmoniError(
                "BMONI balance response is invalid",
                code="BMONI_INVALID_RESPONSE",
            )

        payload = result.get("data", result)

        if not isinstance(payload, dict) or not isinstance(
            payload.get("balances"), list
        ):
            raise BmoniError(
                "BMONI balance response is invalid",
                code="BMONI_INVALID_RESPONSE",
            )

        # The sandbox currently returns this payload at the top level while
        # earlier fixtures used a data envelope. Normalize both at the vendor
        # boundary so application policy consumes one authoritative shape.
        return {"data": payload}

    def create_managed_wallet(
        self,
        *,
        bmoni_user_id: str,
        owner_address: str,
        currency: str,
        challenge_id: str,
        signature: str,
    ) -> dict:
        """Create a managed wallet after owner-proof verification."""
        if self.mode == "mock":
            return {
                "id": f"bm_wal_{uuid.uuid4().hex[:16]}",
                "currency": currency,
                "walletAddress": owner_address,
                "isActive": True,
            }

        existing = next(
            (
                wallet
                for wallet in self.list_wallets(
                    bmoni_user_id=bmoni_user_id
                )
                if wallet.get("currency") == currency
            ),
            None,
        )

        if existing:
            return existing

        try:
            return self._request(
                "POST",
                f"/v1/users/{bmoni_user_id}/smart-wallets/create-managed",
                json_body={
                    "currency": currency,
                    "userOwnerAddress": owner_address,
                    "ownerProofChallengeId": challenge_id,
                    "ownerProofSignature": signature,
                },
            )
        except BmoniError as exc:
            if not exc.retryable:
                raise

            recovered = next(
                (
                    wallet
                    for wallet in self.list_wallets(
                        bmoni_user_id=bmoni_user_id
                    )
                    if wallet.get("currency") == currency
                ),
                None,
            )

            if recovered:
                return recovered

            raise

    def create_withdrawal_proposal(
        self,
        *,
        bmoni_user_id: str,
        amount_minor: int,
        currency: str,
        recipient_name: str,
    ) -> dict:
        """Create a withdrawal proposal used by the transaction flow."""
        if self.mode != "mock":
            self._live_unconfigured("create_withdrawal_proposal")

        return {
            "id": f"bm_prp_{uuid.uuid4().hex[:16]}",
            "status": "PENDING_SIGNATURES",
        }

    def get_fx_quote(
        self,
        *,
        bmoni_user_id: str,
        amount_decimal: str,
        source: str,
        target: str,
    ) -> dict:
        """Request a currency-exchange quote from BMONI."""
        if self.mode != "mock":
            result = self._request(
                "POST",
                f"/v1/users/{bmoni_user_id}/exchange/quote",
                json_body={
                    "swapAmount": {
                        "type": "exactIn",
                        "amountIn": amount_decimal,
                    },
                    "fromCurrency": source,
                    "toCurrency": target,
                },
            )
        else:
            amount_out = Decimal(amount_decimal) / Decimal(1600)

            result = {
                "quoteId": f"bm_qte_{uuid.uuid4().hex[:16]}",
                "fromCurrency": source,
                "toCurrency": target,
                "amountIn": amount_decimal,
                "amountOut": f"{amount_out:.2f}",
                "exchangeRate": "0.000625",
                "toUsdExchangeRate": "0.000625",
                "fees": [],
                "quotedAt": "2099-01-01T00:00:00.000Z",
                "expiresAt": "2099-01-01T00:01:00.000Z",
                "expiresInSeconds": 60,
            }

        return self._validate_fx_quote(
            result,
            amount_decimal=amount_decimal,
            source=source,
            target=target,
        )

    @staticmethod
    def _validate_fx_quote(
        result: Any,
        *,
        amount_decimal: str,
        source: str,
        target: str,
    ) -> dict:
        """Fail closed when a quote is malformed, mismatched, or expired."""
        required = {
            "quoteId",
            "fromCurrency",
            "toCurrency",
            "amountIn",
            "amountOut",
            "exchangeRate",
            "toUsdExchangeRate",
            "fees",
            "quotedAt",
            "expiresAt",
            "expiresInSeconds",
        }

        try:
            if not isinstance(result, dict) or not required.issubset(result):
                raise ValueError

            if not isinstance(result["quoteId"], str) or not result["quoteId"]:
                raise ValueError

            if (
                result["fromCurrency"] != source
                or result["toCurrency"] != target
                or Decimal(result["amountIn"]) != Decimal(amount_decimal)
            ):
                raise ValueError

            for field in ("amountIn", "amountOut", "exchangeRate", "toUsdExchangeRate"):
                value = Decimal(result[field])
                if not value.is_finite() or value <= 0:
                    raise ValueError

            fees = result["fees"]
            if not isinstance(fees, list):
                raise ValueError

            for fee in fees:
                if not isinstance(fee, dict) or not {"currency", "amount"}.issubset(fee):
                    raise ValueError
                fee_amount = Decimal(fee["amount"])
                if not fee_amount.is_finite() or fee_amount < 0:
                    raise ValueError

            quoted_at = datetime.fromisoformat(
                str(result["quotedAt"]).replace("Z", "+00:00")
            )
            expires_at = datetime.fromisoformat(
                str(result["expiresAt"]).replace("Z", "+00:00")
            )
            expires_in_seconds = Decimal(str(result["expiresInSeconds"]))

            if (
                quoted_at.tzinfo is None
                or expires_at.tzinfo is None
                or expires_at <= quoted_at
                or expires_at <= datetime.now(timezone.utc)
                or not expires_in_seconds.is_finite()
                or expires_in_seconds <= 0
            ):
                raise ValueError
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise BmoniError(
                "BMONI returned an invalid or expired FX quote",
                code="BMONI_INVALID_QUOTE",
            ) from exc

        return result

    @staticmethod
    def _proposal(
        result: dict,
        operation: str,
    ) -> dict:
        """Extract and validate a proposal from a BMONI response."""
        try:
            proposal = result["data"]["proposal"]

            if not proposal.get("id") or not proposal.get("status"):
                raise KeyError
        except (KeyError, TypeError) as exc:
            raise BmoniError(
                f"BMONI {operation} response is invalid",
                code="BMONI_INVALID_RESPONSE",
            ) from exc

        return proposal

    def create_swap_proposal(
        self,
        *,
        bmoni_user_id: str,
        smart_wallet_id: str,
        amount_decimal: str,
        from_stablecoin: str = "CNGN",
        to_stablecoin: str = "USDB",
        slippage_bps: int = 50,
    ) -> dict:
        """Create a BMONI swap proposal without executing the swap."""
        if self.mode == "mock":
            return {
                "data": {
                    "proposal": {
                        "id": f"bm_prp_{uuid.uuid4().hex[:16]}",
                        "status": "PENDING_APPROVALS",
                    }
                }
            }

        result = self._request(
            "POST",
            f"/v1/users/{bmoni_user_id}/smart-wallets/{smart_wallet_id}/proposals",
            json_body={
                "proposal": {
                    "type": "SWAP",
                    "fromStablecoin": from_stablecoin,
                    "toStablecoin": to_stablecoin,
                    "fromAmount": amount_decimal,
                    "slippageBps": slippage_bps,
                    "description": "FlowPilot Currency Shield conversion",
                }
            },
        )

        self._proposal(result, "proposal creation")

        return result

    def approve_proposal(
        self,
        *,
        bmoni_user_id: str,
        proposal_id: str,
    ) -> dict:
        """Approve a BMONI swap proposal for signing."""
        if self.mode == "mock":
            return {
                "data": {
                    "proposal": {
                        "id": proposal_id,
                        "status": "PENDING_SIGNATURES",
                    }
                }
            }

        result = self._request(
            "POST",
            f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}/approve",
        )

        self._proposal(result, "proposal approval")

        return result

    def get_proposal(
        self,
        *,
        bmoni_user_id: str,
        proposal_id: str,
    ) -> dict:
        """Retrieve the current state of a BMONI proposal."""
        if self.mode == "mock":
            return {
                "data": {
                    "proposal": {
                        "id": proposal_id,
                        "status": "PENDING_SIGNATURES",
                    }
                }
            }

        result = self._request(
            "GET",
            f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}",
        )

        self._proposal(result, "proposal lookup")

        return result

    def get_proposal_signing_payload(
        self,
        *,
        bmoni_user_id: str,
        proposal_id: str,
    ) -> dict:
        """Retrieve the signing payload required for a BMONI proposal."""
        if self.mode == "mock":
            digest = hashlib.sha256(proposal_id.encode()).hexdigest()

            return {
                "data": {
                    "method": "eth_sign",
                    "walletIndex": 0,
                    "workflowId": f"wf_{proposal_id}",
                    "proposalId": proposal_id,
                    "hashToSign": f"0x{digest}",
                    "payload": {},
                    "deadline": 4102444800,
                }
            }

        result = self._request(
            "GET",
            f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}/sign-payload",
        )

        data = result.get("data") if isinstance(result, dict) else None

        required = {
            "method",
            "walletIndex",
            "workflowId",
            "hashToSign",
            "payload",
            "deadline",
        }

        if not isinstance(data, dict) or not required.issubset(data):
            raise BmoniError(
                "BMONI signing payload is invalid",
                code="BMONI_INVALID_RESPONSE",
            )

        return result

    def submit_proposal_signature(
        self,
        *,
        bmoni_user_id: str,
        proposal_id: str,
        signature: str,
    ) -> dict:
        """Submit a signature for a BMONI proposal."""
        if self.mode == "mock":
            return {
                "data": {
                    "proposal": {
                        "id": proposal_id,
                        "status": "COMPLETED",
                    }
                }
            }

        result = self._request(
            "POST",
            f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}/sign",
            json_body={
                "signature": signature,
            },
        )

        self._proposal(result, "signature submission")

        return result


# Create one gateway instance that the FastAPI application can reuse.
bmoni = BmoniGateway()

