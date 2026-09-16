"""Deterministic LLM client for unit tests. Not used by parse_request by default."""

from __future__ import annotations

import json
from typing import Any


class FakeLLMClient:
    """Return scripted function-call payloads in order."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append(
            {"messages": messages, "tools": tools, "tool_choice": tool_choice}
        )
        if not self._responses:
            raise AssertionError("FakeLLMClient has no remaining scripted responses.")

        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return item
        return json.dumps(item)
