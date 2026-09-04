"""BMONI boundary with a deterministic mock and a fail-closed HTTP client."""

import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings


class BmoniError(RuntimeError):
    def __init__(self, message: str, *, code: str, status_code: int = 502, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class BmoniConfigurationError(BmoniError):
    def __init__(self, message: str):
        super().__init__(message, code="BMONI_NOT_CONFIGURED", status_code=503)


class BmoniConflictError(BmoniError):
    pass


@dataclass
class BmoniGateway:
    mode: str = settings.bmoni_mode

    def _live_unconfigured(self, operation: str) -> None:
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
                message, code="BMONI_CONFLICT", status_code=409
            )
        mapped_status = 422 if response.status_code == 400 else 502
        if response.status_code in {401, 403}:
            mapped_status = 503
        raise BmoniError(
            message,
            code=f"BMONI_HTTP_{response.status_code}",
            status_code=mapped_status,
            retryable=response.status_code == 429 or response.status_code >= 500,
        )

    def _find_user(self, *, external_id: str, email: str) -> dict[str, str] | None:
        page = 1
        while page <= 10:
            result = self._request(
                "GET", "/v1/users", params={"page": page, "limit": 100}
            )
            users = result.get("users", []) if isinstance(result, dict) else []
            for user in users:
                identity_matches = user.get("identityId") == external_id
                email_matches = str(user.get("email", "")).lower() == email.lower()
                if identity_matches or email_matches:
                    return {"id": str(user["bmoniUserId"]), "status": "ACTIVE"}
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
        if self.mode == "mock":
            return {"id": f"bm_usr_{uuid.uuid4().hex[:16]}", "status": "ACTIVE"}
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
            existing = self._find_user(external_id=external_id, email=email)
            if existing:
                return existing
            raise
        try:
            return {"id": str(result["user"]["bmoniUserId"]), "status": "ACTIVE"}
        except (KeyError, TypeError) as exc:
            raise BmoniError(
                "BMONI user response is missing bmoniUserId",
                code="BMONI_INVALID_RESPONSE",
            ) from exc

    def link_wallet(self, *, bmoni_user_id: str, address: str, currency: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("owner-proof wallet provisioning")
        return {"id": f"bm_wal_{uuid.uuid4().hex[:16]}", "status": "ACTIVE"}

    def create_owner_proof_challenge(
        self, *, bmoni_user_id: str, owner_address: str, currency: str
    ) -> dict:
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
            json_body={"currency": currency, "userOwnerAddress": owner_address},
        )

    def list_wallets(self, *, bmoni_user_id: str) -> list[dict]:
        result = self._request(
            "GET", f"/v1/users/{bmoni_user_id}/smart-wallets/account/wallets"
        )
        if not isinstance(result, list):
            raise BmoniError(
                "BMONI wallet response is invalid", code="BMONI_INVALID_RESPONSE"
            )
        return result

    def get_wallet_balances(self, *, bmoni_user_id: str) -> dict:
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
            "GET", f"/v1/users/{bmoni_user_id}/smart-wallets/account/balances"
        )
        if not isinstance(result, dict) or not isinstance(result.get("data"), dict):
            raise BmoniError(
                "BMONI balance response is invalid", code="BMONI_INVALID_RESPONSE"
            )
        return result

    def create_managed_wallet(
        self,
        *,
        bmoni_user_id: str,
        owner_address: str,
        currency: str,
        challenge_id: str,
        signature: str,
    ) -> dict:
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
                for wallet in self.list_wallets(bmoni_user_id=bmoni_user_id)
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
                    for wallet in self.list_wallets(bmoni_user_id=bmoni_user_id)
                    if wallet.get("currency") == currency
                ),
                None,
            )
            if recovered:
                return recovered
            raise

    def create_withdrawal_proposal(
        self, *, bmoni_user_id: str, amount_minor: int, currency: str, recipient_name: str
    ) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("create_withdrawal_proposal")
        return {"id": f"bm_prp_{uuid.uuid4().hex[:16]}", "status": "PENDING_SIGNATURES"}

    def get_signing_payload(self, *, proposal_id: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("get_signing_payload")
        digest = hashlib.sha256(proposal_id.encode()).hexdigest()
        return {"proposal_id": proposal_id, "hash": f"0x{digest}", "algorithm": "ECDSA"}

    def submit_signature(self, *, proposal_id: str, signature: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("submit_signature")
        if not signature.startswith("0x") or len(signature) < 10:
            raise ValueError("Signature must be a non-empty hexadecimal value")
        return {"id": proposal_id, "status": "COMPLETED"}

    def get_fx_quote(
        self,
        *,
        bmoni_user_id: str,
        amount_decimal: str,
        source: str,
        target: str,
    ) -> dict:
        if self.mode != "mock":
            return self._request(
                "POST",
                f"/v1/users/{bmoni_user_id}/exchange/quote",
                json_body={
                    "swapAmount": {"type": "exactIn", "amountIn": amount_decimal},
                    "fromCurrency": source,
                    "toCurrency": target,
                },
            )
        amount_out = Decimal(amount_decimal) / Decimal(1600)
        return {
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

    @staticmethod
    def _proposal(result: dict, operation: str) -> dict:
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
        self, *, bmoni_user_id: str, smart_wallet_id: str,
        amount_decimal: str, from_stablecoin: str = "CNGN",
        to_stablecoin: str = "USDB", slippage_bps: int = 50,
    ) -> dict:
        if self.mode == "mock":
            return {"data": {"proposal": {
                "id": f"bm_prp_{uuid.uuid4().hex[:16]}",
                "status": "PENDING_APPROVALS",
            }}}
        result = self._request(
            "POST", f"/v1/users/{bmoni_user_id}/smart-wallets/{smart_wallet_id}/proposals",
            json_body={"proposal": {
                "type": "SWAP", "fromStablecoin": from_stablecoin,
                "toStablecoin": to_stablecoin, "fromAmount": amount_decimal,
                "slippageBps": slippage_bps,
                "description": "FlowPilot Currency Shield conversion",
            }},
        )
        self._proposal(result, "proposal creation")
        return result

    def approve_proposal(self, *, bmoni_user_id: str, proposal_id: str) -> dict:
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

    def get_proposal(self, *, bmoni_user_id: str, proposal_id: str) -> dict:
        if self.mode == "mock":
            return {"data": {"proposal": {"id": proposal_id, "status": "PENDING_SIGNATURES"}}}
        result = self._request(
            "GET", f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}"
        )
        self._proposal(result, "proposal lookup")
        return result

    def get_proposal_signing_payload(self, *, bmoni_user_id: str, proposal_id: str) -> dict:
        if self.mode == "mock":
            digest = hashlib.sha256(proposal_id.encode()).hexdigest()
            return {"data": {"method": "eth_sign", "walletIndex": 0,
                    "workflowId": f"wf_{proposal_id}", "proposalId": proposal_id,
                    "hashToSign": f"0x{digest}", "payload": {}, "deadline": 4102444800}}
        result = self._request(
            "GET", f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}/sign-payload"
        )
        data = result.get("data") if isinstance(result, dict) else None
        required = {"method", "walletIndex", "workflowId", "hashToSign", "payload", "deadline"}
        if not isinstance(data, dict) or not required.issubset(data):
            raise BmoniError("BMONI signing payload is invalid", code="BMONI_INVALID_RESPONSE")
        return result

    def submit_proposal_signature(
        self, *, bmoni_user_id: str, proposal_id: str, signature: str
    ) -> dict:
        if self.mode == "mock":
            return {"data": {"proposal": {"id": proposal_id, "status": "COMPLETED"}}}
        result = self._request(
            "POST", f"/v1/users/{bmoni_user_id}/smart-wallets/proposals/{proposal_id}/sign",
            json_body={"signature": signature},
        )
        self._proposal(result, "signature submission")
        return result


bmoni = BmoniGateway()
