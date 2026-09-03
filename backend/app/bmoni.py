"""BMONI boundary.

Mock mode is deliberately complete for the hackathon demo. Live mode fails loudly until
the exact BMONI proxy URL, authentication contract, and schemas are confirmed; guesses
about money-moving endpoints must not leak into the rest of the application.
"""

import hashlib
import uuid
from dataclasses import dataclass

from app.config import settings


class BmoniConfigurationError(RuntimeError):
    pass


@dataclass
class BmoniGateway:
    mode: str = settings.bmoni_mode

    def _live_unconfigured(self, operation: str) -> None:
        raise BmoniConfigurationError(
            f"BMONI live operation '{operation}' is not configured. "
            "Set BMONI_MODE=mock for the demo or implement the confirmed vendor schema in app/bmoni.py."
        )

    def create_user(self, *, external_id: str, email: str, name: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("create_user")
        return {"id": f"bm_usr_{uuid.uuid4().hex[:16]}", "status": "ACTIVE"}

    def link_wallet(self, *, bmoni_user_id: str, address: str, currency: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("link_wallet")
        return {"id": f"bm_wal_{uuid.uuid4().hex[:16]}", "status": "ACTIVE"}

    def create_withdrawal_proposal(
        self, *, bmoni_user_id: str, amount_minor: int, currency: str, recipient_name: str
    ) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("create_withdrawal_proposal")
        return {
            "id": f"bm_prp_{uuid.uuid4().hex[:16]}",
            "status": "PENDING_SIGNATURES",
        }

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
        # Demo-only fixture. Never use a hard-coded rate in live mode.
        return {
            "id": f"bm_qte_{uuid.uuid4().hex[:16]}", "source": source, "target": target,
            "source_amount_minor": amount_minor, "target_amount_minor": amount_minor // 1600,
            "rate": "1600.00", "fee_minor": 0, "expires_in_seconds": 60,
        }

    def execute_fx_conversion(self, *, quote_id: str, idempotency_key: str) -> dict:
        if self.mode != "mock":
            self._live_unconfigured("execute_fx_conversion")
        return {"id": f"bm_fx_{uuid.uuid4().hex[:16]}", "status": "COMPLETED", "quote_id": quote_id}


bmoni = BmoniGateway()
