from __future__ import annotations

import os
import uuid
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    # Run behaviour
    max_review_iterations: int = 3
    query_timeout: int = 120
    harness: bool = False
    generate_sql: bool = False
    from_results: bool = False  # skip execution; load pre-run CSVs from results_dir
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])

    # LLM provider: "anthropic" | "groq" | "ollama" | "rule_based"
    # Auto-detected from environment if not set explicitly.
    llm_provider: str = Field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "auto"))

    # Paths
    fixture_dir: str = "tests/fixtures"
    configs_dir: str = "configs"
    runs_dir: str = "runs"
    results_dir: str = "results"

    def fixture_path(self, filename: str) -> Path:
        return Path(self.fixture_dir) / filename

    def run_dir(self) -> Path:
        return Path(self.runs_dir) / self.run_id
