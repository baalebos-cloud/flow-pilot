import os

from .gemini_adapter import GeminiAdapter
from .groq_adapter import GroqAdapter
from .llm_adapter import LLMAdapter
from .resilient_llm_adapter import ResilientLLMAdapter


def build_llm_adapter() -> LLMAdapter:
    """
    Build the Member 3 AI provider stack.

    Default:
        Gemini

    If both Gemini and Groq API keys are available:
        Gemini -> Groq fallback

    If only Gemini is available:
        Gemini only

    If only Groq is available:
        Groq only

    The selected provider is only an interpreter.
    No provider can execute financial actions.
    """

    provider = os.getenv(
        "FLOWPILOT_LLM_PROVIDER",
        "gemini",
    ).strip().lower()

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    if provider == "gemini":
        if not gemini_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set."
            )

        primary = GeminiAdapter()

        if groq_key:
            return ResilientLLMAdapter(
                primary=primary,
                fallback=GroqAdapter(),
            )

        return primary

    if provider == "groq":
        if not groq_key:
            raise RuntimeError(
                "GROQ_API_KEY environment variable is not set."
            )

        return GroqAdapter()

    raise ValueError(
        f"Unsupported LLM provider: '{provider}'. "
        "Supported providers are: gemini, groq."
    )