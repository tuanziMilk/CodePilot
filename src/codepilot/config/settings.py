"""Typed runtime configuration.

The model provider is configured here rather than referenced by the Agent Harness.
That separation is what allows DeepSeek to be swapped without changing the loop.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, field_validator


class Settings(BaseModel):
    """Configuration required to construct a Phase-1 run.

    api_key remains a SecretStr so accidental repr/model_dump calls do not expose it.
    Use redacted_snapshot whenever configuration is persisted.
    """

    llm_provider: str = "deepseek"
    llm_model: str
    llm_base_url: str
    llm_api_key: SecretStr
    llm_temperature: float = Field(default=0, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=4096, ge=1)
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_request_retries: int = Field(default=2, ge=0)
    git_bash_path: Path = Path(r"E:\Git\bin\bash.exe")
    agent_max_steps: int = Field(default=12, ge=1)
    agent_max_retries: int = Field(default=1, ge=0)
    tool_policy_version: str = "mvp-v1"
    prompt_version: str = "mvp-v1"
    command_timeout_seconds: float = Field(default=60, gt=0)

    @field_validator("llm_provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("llm_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("LLM_BASE_URL must be an HTTP(S) endpoint.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("LLM_BASE_URL must not contain credentials, query parameters or fragments.")
        return value.rstrip("/")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        """Load settings without persisting the API key anywhere."""

        selected_env = env_file or Path(os.environ.get("CODEPILOT_ENV_FILE", Path.cwd() / ".env"))
        load_dotenv(selected_env, override=False)

        def required(name: str) -> str:
            value = os.getenv(name)
            if not value:
                raise ValueError(f"Missing required configuration: {name}")
            if value.startswith("REPLACE_WITH_"):
                raise ValueError(f"Fill in your local configuration: {name}")
            return value

        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
            llm_model=required("LLM_MODEL"),
            llm_base_url=required("LLM_BASE_URL"),
            llm_api_key=SecretStr(required("LLM_API_KEY")),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            llm_max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096")),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            llm_request_retries=int(os.getenv("LLM_REQUEST_RETRIES", "2")),
            git_bash_path=Path(os.getenv("GIT_BASH_PATH", r"E:\Git\bin\bash.exe")),
            agent_max_steps=int(os.getenv("AGENT_MAX_STEPS", "12")),
            agent_max_retries=int(os.getenv("AGENT_MAX_RETRIES", "1")),
            tool_policy_version=os.getenv("TOOL_POLICY_VERSION", "mvp-v1"),
            prompt_version=os.getenv("PROMPT_VERSION", "mvp-v1"),
            command_timeout_seconds=float(os.getenv("COMMAND_TIMEOUT_SECONDS", "60")),
        )

    def base_url_identifier(self) -> str:
        """Return a non-secret identifier suitable for metadata."""

        return urlsplit(self.llm_base_url).netloc

    def redacted_snapshot(self) -> dict[str, object]:
        """Return the only configuration representation allowed in artifacts."""

        return {
            "provider": self.llm_provider,
            "model": self.llm_model,
            "base_url_identifier": self.base_url_identifier(),
            "temperature": self.llm_temperature,
            "max_output_tokens": self.llm_max_output_tokens,
            "timeout_seconds": self.llm_timeout_seconds,
            "llm_request_retries": self.llm_request_retries,
            "git_bash_path": str(self.git_bash_path),
            "agent_max_steps": self.agent_max_steps,
            "agent_max_retries": self.agent_max_retries,
            "tool_policy_version": self.tool_policy_version,
            "prompt_version": self.prompt_version,
            "command_timeout_seconds": self.command_timeout_seconds,
        }
