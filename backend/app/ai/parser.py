import json

from pydantic import ValidationError

from .models import EXECUTABLE_ACTIONS, READ_ONLY_ACTIONS, FinancialIntent


def enforce_approval_policy(intent: FinancialIntent) -> FinancialIntent:
    """
    Deterministically enforce the approval requirement.

    The LLM may suggest a value, but the application decides whether
    approval is required.
    """

    if intent.action_type in EXECUTABLE_ACTIONS:
        intent.requires_user_approval = True

    elif intent.action_type in READ_ONLY_ACTIONS:
        intent.requires_user_approval = False

    return intent


def parse_financial_intent(raw_response: str) -> FinancialIntent:
    """
    Convert the provider's JSON response into a validated FinancialIntent.

    No financial action is executed here.
    """

    if not raw_response or not raw_response.strip():
        raise ValueError("Empty AI response")

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError("AI response is not valid JSON") from exc

    if data.get("needs_clarification") and not data.get(
        "clarification_question"
    ):
        raise ValueError(
            "AI requested clarification but did not provide a question."
        )

    try:
        intent = FinancialIntent.model_validate(data)
    except ValidationError as exc:
        raise ValueError(
            f"AI response failed FinancialIntent validation: {exc}"
        ) from exc

    return enforce_approval_policy(intent)