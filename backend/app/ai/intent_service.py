from .llm_factory import create_llm_adapter
from .models import FinancialIntent
from .parser import parse_financial_intent


class IntentService:
    """
    Main Member 3 AI entry point.

    The service:
        user message
            ↓
        LLM provider
            ↓
        JSON
            ↓
        Pydantic validation
            ↓
        FinancialIntent

    It does NOT execute transactions.
    """

    def __init__(self, adapter=None):
        self.adapter = adapter or create_llm_adapter()

    def extract_intent(self, user_message: str) -> FinancialIntent:
        if not user_message or not user_message.strip():
            raise ValueError("user_message cannot be empty")

        raw_response = self.adapter.generate_intent(user_message)

        return parse_financial_intent(raw_response)