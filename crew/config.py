"""Loads crew.toml and the prompt files."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROLES = ("analyst", "architect", "coder", "tester", "debugger", "reviewer")


@dataclass(frozen=True)
class AgentConfig:
    model: str
    temperature: float
    max_tokens: int
    system_prompt: str


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    timeout_s: float
    agents: dict[str, AgentConfig]
    max_fix_rounds: int
    test_timeout_s: int
    use_venv: bool
    context_chars: int


def load_config(path: Path, require_model: bool = True) -> Config:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    server = raw.get("server", {})
    defaults = raw.get("defaults", {})
    pipeline = raw.get("pipeline", {})

    agents: dict[str, AgentConfig] = {}
    for role in ROLES:
        merged = {**defaults, **raw.get("agents", {}).get(role, {})}
        model = merged.get("model", "")
        if require_model and not model:
            raise SystemExit(
                f"No model set for '{role}'. Put a model id in [defaults] of {path.name} "
                "(run `python -m crew models` to list what LM Studio has)."
            )
        prompt_file = root / "prompts" / f"{role}.md"
        agents[role] = AgentConfig(
            model=model,
            temperature=float(merged.get("temperature", 0.2)),
            max_tokens=int(merged.get("max_tokens", 8192)),
            system_prompt=prompt_file.read_text(encoding="utf-8").strip(),
        )

    return Config(
        base_url=server.get("base_url", "http://localhost:1234/v1"),
        api_key=server.get("api_key", "lm-studio"),
        timeout_s=float(server.get("timeout_s", 900)),
        agents=agents,
        max_fix_rounds=int(pipeline.get("max_fix_rounds", 5)),
        test_timeout_s=int(pipeline.get("test_timeout_s", 120)),
        use_venv=bool(pipeline.get("use_venv", True)),
        context_chars=int(pipeline.get("context_chars", 60000)),
    )
