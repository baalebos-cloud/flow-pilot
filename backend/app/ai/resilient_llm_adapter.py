from .llm_adapter import LLMAdapter


class ResilientLLMAdapter(LLMAdapter):
    """
    Provider-resilient Member 3 adapter.

    Primary provider is attempted first.
    The fallback provider is used only when the primary provider
    appears temporarily unavailable.

    This layer performs interpretation only.
    It never executes financial actions.
    """

    def __init__(
        self,
        primary: LLMAdapter,
        fallback: LLMAdapter,
    ):
        self.primary = primary
        self.fallback = fallback

    def generate_recommendation(self, request) -> str:
        try:
            return self.primary.generate_recommendation(request)

        except Exception as exc:
            if not self._is_provider_failure(exc):
                raise

            print(
                "MEMBER3 PRIMARY PROVIDER UNAVAILABLE: "
                f"{type(exc).__name__}: {exc}"
            )

            print(
                "MEMBER3 FALLBACK: switching to secondary provider."
            )

            return self.fallback.generate_recommendation(request)

    @staticmethod
    def _is_provider_failure(exc: Exception) -> bool:
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