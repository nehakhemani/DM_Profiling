from __future__ import annotations

import json

from .config import Settings
from .models import EntityConfig


def extract_entity_config(raw_text: str, settings: Settings) -> tuple[EntityConfig, list[str]]:
    """
    Parses plain-text intake into an EntityConfig draft plus any clarification questions.

    Harness: loads tests/fixtures/entity_config.json, returns no clarifications.
    Real (Phase 4): calls LLM with the §5.1 prompts; retries once on parse failure.

    Returns:
        (EntityConfig, clarifications) — if clarifications is non-empty the pipeline
        must print them and exit without proceeding.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("entity_config.json").read_text(encoding="utf-8"))
        return EntityConfig.model_validate(raw), []

    raise NotImplementedError("Live extractor not yet implemented — use --harness")
