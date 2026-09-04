import json
import asyncio
import re
from typing import Any

from .contracts import (
    BankWithdrawalParameters,
    ModelFailure,
    RecommendationOutcome,
    RecommendationRequest,
    RecommendationResult,
    RecommendationType,
)
from .llm_factory import build_llm_adapter
from .llm_adapter import LLMAdapter


class Member3Engine:
    """
    Member 3 AI recommendation engine.

    Responsibilities:
    - Send sanitized requests to the selected LLM provider.
    - Parse and validate structured model output.
    - Normalize provider-specific output differences.
    - Enforce deterministic semantic checks.
    - Never execute financial actions.

    The AI proposes an action.
    Backend policy and user approval remain authoritative.
    """

    def __init__(
        self,
        adapter: LLMAdapter | None = None,
    ):
        self.adapter = adapter or build_llm_adapter()

    async def recommend(
        self,
        request: RecommendationRequest,
    ) -> RecommendationOutcome:
        try:
            raw_output = await asyncio.to_thread(
                self.adapter.generate_recommendation, request
            )

            data = self._parse_json(raw_output)

            normalized = self._normalize_output(
                data,
                request,
            )

            outcome = RecommendationOutcome.model_validate(
                normalized
            )

            self._validate_request_id(
                outcome,
                request,
            )

            self._validate_context_references(
                outcome,
                request,
            )

            outcome = self._normalize_explicit_amount(
                outcome,
                request,
            )

            self._validate_recommendation_semantics(
                outcome,
                request,
            )

            return outcome

        except Exception as exc:
            if isinstance(exc, ValueError):
                return self._model_error(
                    request,
                    error_code="INVALID_OUTPUT",
                    retryable=False,
                )

            if self._is_provider_failure(exc):
                return self._model_error(
                    request,
                    error_code="PROVIDER_UNAVAILABLE",
                    retryable=True,
                )

            return self._model_error(
                request,
                error_code="INTERNAL_ERROR",
                retryable=False,
            )

    @staticmethod
    def _parse_json(
        raw_output: str,
    ) -> dict[str, Any]:
        if not raw_output or not raw_output.strip():
            raise ValueError("Empty model output.")

        text = raw_output.strip()

        if text.startswith("```"):
            text = re.sub(
                r"^```(?:json)?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )

            text = re.sub(
                r"\s*```$",
                "",
                text,
            )

        data = json.loads(text)

        if not isinstance(data, dict):
            raise ValueError(
                "Model output must be a JSON object."
            )

        return data

    @staticmethod
    def _normalize_output(
        data: dict[str, Any],
        request: RecommendationRequest,
    ) -> dict[str, Any]:
        normalized = dict(data)

        normalized.setdefault(
            "schema_version",
            request.schema_version,
        )

        normalized.setdefault(
            "request_id",
            request.request_id,
        )

        return normalized

    @staticmethod
    def _validate_request_id(
        outcome: RecommendationOutcome,
        request: RecommendationRequest,
    ) -> None:
        value = outcome.root

        if value.request_id != request.request_id:
            raise ValueError(
                "Model returned an invalid request_id."
            )

    @staticmethod
    def _validate_context_references(
        outcome: RecommendationOutcome,
        request: RecommendationRequest,
    ) -> None:
        value = outcome.root

        if not isinstance(
            value,
            RecommendationResult,
        ):
            return

        valid_references = {
            pocket.reference_id
            for pocket in request.context.pockets
        }

        valid_references.update(
            recipient.reference_id
            for recipient in request.context.recipients
        )

        valid_references.update(
            observation.reference_id
            for observation in request.context.market_observations
        )

        valid_references.update(
            opportunity.reference_id
            for opportunity in request.context.investment_opportunities
        )

        parameters = value.parameters

        referenced_ids: list[str] = []

        for field_name in (
            "recipient_reference_id",
            "source_pocket_reference_id",
            "target_pocket_reference_id",
            "pocket_reference_id",
            "market_observation_reference_id",
            "opportunity_reference_id",
        ):
            reference = getattr(
                parameters,
                field_name,
                None,
            )

            if reference:
                referenced_ids.append(reference)

        referenced_ids.extend(
            getattr(
                parameters,
                "pocket_reference_ids",
                [],
            )
        )

        for reference_id in referenced_ids:
            if reference_id not in valid_references:
                raise ValueError(
                    f"Model referenced unknown context ID: "
                    f"{reference_id}"
                )

    @staticmethod
    def _extract_single_explicit_amount(
        message: str,
    ) -> int | None:
        """
        Extract one explicit user-provided whole-naira amount.

        Examples:
            100000
            100,000
            ₦100000
            ₦100,000
            100000 naira
            NGN 100000

        User-entered naira values are major units. The backend contract uses
        minor units, so 100000 naira becomes 10000000 kobo.
        """

        pattern = re.compile(
            r"""
            (?:
                ₦\s*
                |
                NGN\s*
            )?
            (
                \d{1,3}(?:,\d{3})+
                |
                \d+
            )
            \s*
            (?:naira|NGN)?
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        matches = pattern.findall(message)

        if not matches:
            return None

        values: list[int] = []

        for match in matches:
            try:
                value = int(
                    match.replace(",", "")
                )
            except ValueError:
                continue

            if value > 0:
                values.append(value)

        unique_values = set(values)

        if len(unique_values) != 1:
            return None

        return values[0] * 100

    @classmethod
    def _normalize_explicit_amount(
        cls,
        outcome: RecommendationOutcome,
        request: RecommendationRequest,
    ) -> RecommendationOutcome:
        """
        Convert an explicit whole-naira amount to the backend's minor units.
        """

        value = outcome.root

        if not isinstance(
            value,
            RecommendationResult,
        ):
            return outcome

        explicit_amount = cls._extract_single_explicit_amount(
            request.user_message
        )

        if explicit_amount is None:
            return outcome

        parameters = value.parameters

        updates: dict[str, Any] = {}

        for field_name in (
            "amount_minor",
            "suggested_amount_minor",
            "allocated_minor",
        ):
            if hasattr(
                parameters,
                field_name,
            ):
                updates[field_name] = explicit_amount
                break

        if not updates:
            return outcome

        updated_parameters = parameters.model_copy(
            update=updates
        )

        explanation = value.explanation

        if (
            value.recommendation_type
            == RecommendationType.BANK_WITHDRAWAL
        ):
            explanation = (
                f"Recommendation to withdraw "
                f"{explicit_amount // 100:,} CNGN to your saved bank "
                f"account as requested."
            )

        updated_result = value.model_copy(
            update={
                "parameters": updated_parameters,
                "explanation": explanation,
            }
        )

        return RecommendationOutcome(
            root=updated_result
        )

    @staticmethod
    def _validate_recommendation_semantics(
        outcome: RecommendationOutcome,
        request: RecommendationRequest,
    ) -> None:
        value = outcome.root

        if not isinstance(
            value,
            RecommendationResult,
        ):
            return

        # The recommendation type and parameter kind must
        # always describe the exact same financial action.
        if value.recommendation_type != value.parameters.kind:
            raise ValueError(
                "Recommendation type does not match "
                "parameters kind."
            )

        # AI cannot recommend an action that the backend
        # explicitly did not allow.
        if (
            value.recommendation_type
            not in request.context.allowed_recommendation_types
        ):
            raise ValueError(
                "Recommendation type is not allowed "
                "by the backend request."
            )

        # Financial actions must always require explicit
        # user approval before execution.
        if value.recommendation_type in {
            RecommendationType.TRANSFER,
            RecommendationType.BANK_WITHDRAWAL,
            RecommendationType.POCKET_TRANSFER,
            RecommendationType.CURRENCY_PROTECTION,
            RecommendationType.INVESTMENT_DISCOVERY,
        }:
            if not value.requires_user_approval:
                raise ValueError(
                    "Financial recommendations must require "
                    "user approval."
                )

        # BANK_WITHDRAWAL-specific validation.
        if (
            value.recommendation_type
            == RecommendationType.BANK_WITHDRAWAL
        ):
            if not isinstance(
                value.parameters,
                BankWithdrawalParameters,
            ):
                raise ValueError(
                    "BANK_WITHDRAWAL requires "
                    "BankWithdrawalParameters."
                )

            if (
                value.parameters.currency
                != request.context.base_currency
            ):
                raise ValueError(
                    "Recommendation currency does not match "
                    "the request base currency."
                )

    @staticmethod
    def _is_provider_failure(
        exc: Exception,
    ) -> bool:
        message = str(exc).lower()

        provider_terms = (
            "api key",
            "authentication",
            "unauthorized",
            "rate limit",
            "timeout",
            "connection",
            "service unavailable",
            "temporarily unavailable",
            "resource exhausted",
            "quota",
            "429",
            "500",
            "502",
            "503",
            "504",
            "unavailable",
        )

        return any(
            term in message
            for term in provider_terms
        )

    @staticmethod
    def _model_error(
        request: RecommendationRequest,
        error_code: str,
        retryable: bool,
    ) -> RecommendationOutcome:
        failure = ModelFailure(
            outcome="MODEL_ERROR",
            schema_version=request.schema_version,
            request_id=request.request_id,
            error_code=error_code,
            retryable=retryable,
        )

        return RecommendationOutcome(
            root=failure
        )
