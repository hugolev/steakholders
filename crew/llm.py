"""Thin wrapper around LM Studio's OpenAI-compatible server.

Two call styles, chosen per agent:
- JSON agents (analyst, architect, reviewer) pass a JSON schema; LM Studio constrains the
  output to it, so the reply always parses.
- Code agents (coder, tester, debugger) return plain text with fenced file blocks. Local
  models write noticeably worse code when it has to be escaped inside a JSON string.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import Config

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, cfg: Config, log_dir: Path | None = None):
        from openai import OpenAI  # imported here so tests can run without the package

        self.cfg = cfg
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=cfg.timeout_s)
        self.log_dir = log_dir
        self._n = 0

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self.client.models.list().data)

    def complete(self, role: str, user: str, schema: dict | None = None) -> Any:
        """Returns a dict when `schema` is given, otherwise the reply text."""
        agent = self.cfg.agents[role]
        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": role, "strict": True, "schema": schema},
            }
        last_error = ""
        for attempt in range(3):
            resp = self.client.chat.completions.create(
                model=agent.model,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                messages=[
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": user},
                ],
                **kwargs,
            )
            choice = resp.choices[0]
            text = _THINK.sub("", choice.message.content or "").strip()
            self._log(role, user, text)
            if choice.finish_reason == "length":
                last_error = (
                    f"reply hit max_tokens ({agent.max_tokens}); raise it for '{role}' in crew.toml "
                    "or raise the model's context length in LM Studio"
                )
                continue
            if schema is None:
                if text:
                    return text
                last_error = "empty reply"
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = f"invalid JSON: {exc}"
        raise LLMError(f"{role}: {last_error}")

    def _log(self, role: str, user: str, reply: str) -> None:
        if self.log_dir is None:
            return
        self._n += 1
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / f"{self._n:03d}_{role}.md").write_text(
            f"# PROMPT\n\n{user}\n\n# REPLY\n\n{reply}\n", encoding="utf-8"
        )
