from abc import ABC, abstractmethod

from .contracts import RecommendationRequest


class LLMAdapter(ABC):
    """
    Common interface for Member 3 AI providers.

    Providers interpret the sanitized backend request and return
    structured recommendation output.

    Providers never execute transactions, access private keys,
    or make final policy/approval decisions.
    """

    @abstractmethod
    def generate_recommendation(
        self,
        request: RecommendationRequest,
    ) -> str:
        raise NotImplementedError
