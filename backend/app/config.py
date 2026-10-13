"""Settings loaded from environment variables (optionally from a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional .env support
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "ollama").lower())
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    )
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    llm_timeout_sec: int = field(default_factory=lambda: _int("LLM_TIMEOUT_SEC", 120))
    test_timeout_sec: int = field(default_factory=lambda: _int("TEST_TIMEOUT_SEC", 30))
    coverage_threshold: float = field(default_factory=lambda: _float("COVERAGE_THRESHOLD", 60))
    max_functions_default: int = field(default_factory=lambda: _int("MAX_FUNCTIONS_DEFAULT", 10))
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 50))
    max_zip_files: int = field(default_factory=lambda: _int("MAX_ZIP_FILES", 5000))
    workspace_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("WORKSPACE_DIR", "./data/jobs")).resolve()
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.environ.get(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        ]
    )
    deps_install_timeout_sec: int = field(default_factory=lambda: _int("DEPS_INSTALL_TIMEOUT_SEC", 120))
    clone_timeout_sec: int = field(default_factory=lambda: _int("CLONE_TIMEOUT_SEC", 300))
    workspace_max_age_hours: int = field(default_factory=lambda: _int("WORKSPACE_MAX_AGE_HOURS", 24))
    risk_weight_recency: float = field(default_factory=lambda: _float("RISK_WEIGHT_RECENCY", 0.5))
    risk_weight_usage: float = field(default_factory=lambda: _float("RISK_WEIGHT_USAGE", 0.5))


settings = Settings()


def reload_settings() -> Settings:
    """Re-read the environment (used by tests)."""
    global settings
    settings = Settings()
    return settings


def get_settings() -> Settings:
    return settings
