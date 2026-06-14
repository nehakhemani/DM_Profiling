from __future__ import annotations

from .config import Settings


def call_llm(system_prompt: str, user_prompt: str, settings: Settings) -> str:
    """Thin wrapper around the Anthropic SDK. Implemented in Phase 4+."""
    raise NotImplementedError(
        "LLM client not yet implemented — run with --harness for fixture-based mode"
    )
