from dataclasses import dataclass

from app.ai.contracts import (
    BankWithdrawalParameters,
    CurrencyProtectionParameters,
    InvestmentDiscoveryParameters,
    PocketTransferParameters,
    RecommendationRequest,
    RecommendationResult,
    RecommendationType,
    SpendingAnalysisParameters,
    TransferParameters,
)


class ContractPolicyError(ValueError):
    pass


APPROVAL_REQUIRED_TYPES = frozenset(
    {
        RecommendationType.TRANSFER,
        RecommendationType.BANK_WITHDRAWAL,
        RecommendationType.POCKET_TRANSFER,
        RecommendationType.CURRENCY_PROTECTION,
    }
)


@dataclass(frozen=True)
class ValidatedRecommendation:
    recommendation: RecommendationResult
    requires_user_approval: bool


def validate_recommendation(
    request: RecommendationRequest, recommendation: RecommendationResult
) -> ValidatedRecommendation:
    if recommendation.request_id != request.request_id:
        raise ContractPolicyError("AI response request_id does not match request")
    if recommendation.recommendation_type not in request.context.allowed_recommendation_types:
        raise ContractPolicyError("Recommendation type was not allowed in this request")
    if recommendation.parameters.kind != recommendation.recommendation_type:
        raise ContractPolicyError("Recommendation type does not match parameter type")

    pocket_ids = {item.reference_id for item in request.context.pockets}
    recipient_ids = {item.reference_id for item in request.context.recipients}
    observation_ids = {item.reference_id for item in request.context.market_observations}
    opportunity_ids = {item.reference_id for item in request.context.investment_opportunities}
    supplied_evidence_ids = observation_ids | opportunity_ids

    unknown_evidence = set(recommendation.evidence_reference_ids) - supplied_evidence_ids
    if unknown_evidence:
        raise ContractPolicyError("Recommendation contains an unknown evidence reference")

    parameters = recommendation.parameters
    if isinstance(parameters, (TransferParameters, BankWithdrawalParameters)):
        _require_reference(parameters.recipient_reference_id, recipient_ids, "recipient")
    elif isinstance(parameters, PocketTransferParameters):
        _require_reference(parameters.source_pocket_reference_id, pocket_ids, "source pocket")
        _require_reference(parameters.target_pocket_reference_id, pocket_ids, "target pocket")
        if parameters.source_pocket_reference_id == parameters.target_pocket_reference_id:
            raise ContractPolicyError("Pocket transfer source and target must differ")
    elif isinstance(parameters, CurrencyProtectionParameters):
        _require_reference(parameters.pocket_reference_id, pocket_ids, "pocket")
        _require_reference(parameters.market_observation_reference_id, observation_ids, "market observation")
        pocket = next(item for item in request.context.pockets if item.reference_id == parameters.pocket_reference_id)
        if pocket.protected:
            raise ContractPolicyError("Protected pockets cannot fund Currency Shield")
        if parameters.suggested_amount_minor > pocket.available_minor:
            raise ContractPolicyError("Currency Shield amount exceeds the supplied pocket balance")
        if parameters.source_currency != pocket.currency:
            raise ContractPolicyError("Currency Shield source currency does not match the pocket")
        observation = next(
            item
            for item in request.context.market_observations
            if item.reference_id == parameters.market_observation_reference_id
        )
        if (
            observation.source_currency != parameters.source_currency
            or observation.target_currency != parameters.target_currency
        ):
            raise ContractPolicyError("Currency Shield pair does not match its market evidence")
        if parameters.market_observation_reference_id not in recommendation.evidence_reference_ids:
            raise ContractPolicyError("Currency Shield must cite its market observation")
    elif isinstance(parameters, SpendingAnalysisParameters):
        if set(parameters.pocket_reference_ids) - pocket_ids:
            raise ContractPolicyError("Spending analysis contains an unknown pocket reference")
    elif isinstance(parameters, InvestmentDiscoveryParameters):
        _require_reference(parameters.pocket_reference_id, pocket_ids, "pocket")
        _require_reference(parameters.opportunity_reference_id, opportunity_ids, "investment opportunity")
        pocket = next(item for item in request.context.pockets if item.reference_id == parameters.pocket_reference_id)
        opportunity = next(
            item
            for item in request.context.investment_opportunities
            if item.reference_id == parameters.opportunity_reference_id
        )
        if parameters.suggested_amount_minor > pocket.available_minor:
            raise ContractPolicyError("Investment amount exceeds the supplied pocket balance")
        if parameters.currency != pocket.currency or parameters.currency != opportunity.currency:
            raise ContractPolicyError("Investment currency does not match supplied context")
        if parameters.opportunity_reference_id not in recommendation.evidence_reference_ids:
            raise ContractPolicyError("Investment discovery must cite its verified opportunity")

    required = recommendation.recommendation_type in APPROVAL_REQUIRED_TYPES
    return ValidatedRecommendation(recommendation=recommendation, requires_user_approval=required)


def _require_reference(reference_id: str, allowed: set[str], label: str) -> None:
    if reference_id not in allowed:
        raise ContractPolicyError(f"Recommendation contains an unknown {label} reference")
