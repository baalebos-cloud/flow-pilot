"""BMONI boundary with a deterministic mock and a fail-closed HTTP client."""

import hashlib
import uuid
from dataclasses import dataclass
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

    def get_fx_quote(self, *, amount_minor: int, source: str, target: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("get_fx_quote")
        return {
            "id": f"bm_qte_{uuid.uuid4().hex[:16]}",
            "source": source,
            "target": target,
            "source_amount_minor": amount_minor,
            "target_amount_minor": amount_minor // 1600,
            "rate": "1600.00",
            "fee_minor": 0,
            "expires_in_seconds": 60,
        }

    def execute_fx_conversion(self, *, quote_id: str, idempotency_key: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("execute_fx_conversion")
        return {
            "id": f"bm_fx_{uuid.uuid4().hex[:16]}",
            "status": "COMPLETED",
            "quote_id": quote_id,
        }


bmoni = BmoniGateway()
