"""BMONI integration boundary.

This module keeps BMONI-specific communication in one place so the rest of
the application can work with a small, predictable gateway interface.
"""

import hashlib
import uuid
from dataclasses import dataclass

import httpx

from app.config import settings


class BmoniConfigurationError(RuntimeError):
    """Raised when the BMONI live integration is missing required configuration."""


class BmoniAPIError(RuntimeError):
    """Raised when the BMONI API rejects a request or returns an invalid response."""


@dataclass
class BmoniGateway:
    """Provide the application with the operations it needs from BMONI."""

    mode: str = settings.bmoni_mode
    base_url: str = settings.bmoni_base_url
    api_key: str = settings.bmoni_api_key

    # Build the authentication headers required for every BMONI API request.
    def _headers(self) -> dict:
        """Return the headers required to authenticate with BMONI."""
        if not self.api_key:
            raise BmoniConfigurationError(
                "BMONI_API_KEY is required when BMONI_MODE=live."
            )

        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    # Send an HTTP request to BMONI and turn vendor errors into application errors.
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
    ) -> dict:
        """Send an authenticated request to BMONI."""
        if not self.base_url:
            raise BmoniConfigurationError(
                "BMONI_BASE_URL is required when BMONI_MODE=live."
            )

        url = f"{self.base_url.rstrip('/')}{path}"

        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                timeout=20.0,
            )
        except httpx.RequestError as exc:
            raise BmoniAPIError(f"Unable to reach BMONI: {exc}") from exc

        if response.is_error:
            raise BmoniAPIError(
                f"BMONI returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise BmoniAPIError(
                "BMONI returned a response that was not valid JSON."
            ) from exc

    # Create the BMONI user required before the application can provision a wallet.
    def create_user(
        self,
        *,
        external_id: str,
        email: str,
        name: str,
        phone_number: str,
    ) -> dict:
        """Create a user in BMONI using the application's registration details."""

        # Keep mock mode available so automated tests can run without
        # depending on the external BMONI sandbox.
        if self.mode != "live":
            return {
                "id": f"bm_usr_{uuid.uuid4().hex[:16]}",
                "status": "ACTIVE",
            }

        # Split the application's display name into the fields BMONI expects.
        first_name, _, last_name = name.partition(" ")

        # Send the required registration information to BMONI.
        return self._request(
            "POST",
            "/v1/users",
            json={
                "firstName": first_name,
                "lastName": last_name or first_name,
                "email": email,
                "phoneNumber": phone_number,
            },
        )

    # Provision a managed smart wallet for the BMONI user.
    def link_wallet(
        self,
        *,
        bmoni_user_id: str,
        address: str,
        currency: str,
    ) -> dict:
        """Provision the managed wallet associated with a BMONI user."""

        # Return a predictable fake wallet when the application is running in mock mode.
        if self.mode != "live":
            return {
                "id": f"bm_wal_{uuid.uuid4().hex[:16]}",
                "status": "ACTIVE",
            }

        # BMONI's managed-wallet endpoint provisions the wallet for the user.
        return self._request(
            "POST",
            f"/v1/users/{bmoni_user_id}/smart-wallets/create-managed",
            json={},
        )

    # Create a withdrawal proposal used by the existing transaction flow.
    def create_withdrawal_proposal(
        self,
        *,
        bmoni_user_id: str,
        amount_minor: int,
        currency: str,
        recipient_name: str,
    ) -> dict:
        """Create a withdrawal proposal for a BMONI smart wallet."""

        # Preserve the existing deterministic application behavior in mock mode.
        if self.mode != "live":
            return {
                "id": f"bm_prp_{uuid.uuid4().hex[:16]}",
                "status": "PENDING_SIGNATURES",
            }

        # The exact withdrawal proposal payload still needs to be matched
        # against the team's confirmed BMONI transaction schema.
        raise BmoniConfigurationError(
            "Live withdrawal proposal schema has not been confirmed."
        )

    # Return the signing payload associated with a transaction proposal.
    def get_signing_payload(
        self,
        *,
        proposal_id: str,
    ) -> dict:
        """Retrieve the payload that the application must sign."""

        # Use the existing deterministic fixture during local testing.
        if self.mode != "live":
            digest = hashlib.sha256(proposal_id.encode()).hexdigest()

            return {
                "proposal_id": proposal_id,
                "hash": f"0x{digest}",
                "algorithm": "ECDSA",
            }

        # The live BMONI signing endpoint requires a user ID, which the
        # current gateway method does not receive yet.
        raise BmoniConfigurationError(
            "Live signing payload integration requires the confirmed BMONI user context."
        )

    # Submit a transaction signature in mock mode while keeping the live
    # implementation deliberately disabled until its exact schema is wired.
    def submit_signature(
        self,
        *,
        proposal_id: str,
        signature: str,
    ) -> dict:
        """Submit a signature for a BMONI proposal."""

        # Validate the signature before accepting it in mock mode.
        if self.mode != "live":
            if not signature.startswith("0x") or len(signature) < 10:
                raise ValueError(
                    "Signature must be a non-empty hexadecimal value"
                )

            return {
                "id": proposal_id,
                "status": "COMPLETED",
            }

        raise BmoniConfigurationError(
            "Live signature submission schema has not been confirmed."
        )

    # Request an exchange quote from BMONI for Currency Shield.
    def get_fx_quote(
        self,
        *,
        user_id: str,
        amount_minor: int,
        source: str,
        target: str,
    ) -> dict:
        """Create a currency-exchange quote for the requested amount."""

        # Use a deterministic fixture for the existing automated demo flow.
        if self.mode != "live":
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

        # Use BMONI's documented user-level exchange quote endpoint.
        return self._request(
            "POST",
            f"/v1/users/{user_id}/exchange/quote",
            json={
                "sourceCurrency": source,
                "targetCurrency": target,
                "amount": str(amount_minor),
            },
        )

    # Execute a previously created Currency Shield exchange.
    def execute_fx_conversion(
        self,
        *,
        user_id: str,
        quote_id: str,
        idempotency_key: str,
    ) -> dict:
        """Execute a previously generated BMONI exchange quote."""

        # Return a completed fixture during mock-mode tests.
        if self.mode != "live":
            return {
                "id": f"bm_fx_{uuid.uuid4().hex[:16]}",
                "status": "COMPLETED",
                "quote_id": quote_id,
            }

        # Execute the conversion through BMONI's exchange endpoint.
        return self._request(
            "POST",
            f"/v1/users/{user_id}/exchange/convert",
            json={
                "quoteId": quote_id,
                "idempotencyKey": idempotency_key,
            },
        )


# Create one gateway instance that the FastAPI application can reuse.
bmoni = BmoniGateway()