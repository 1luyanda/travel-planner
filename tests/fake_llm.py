"""Deterministic LLM client for unit tests. Not used by parse_request by default."""

from __future__ import annotations

import asyncio
import json
from typing import Any


class FakeLLMClient:
    """Return scripted function-call payloads in order."""

    def __init__(
        self,
        responses: list[Any],
        *,
        delay_seconds: float = 0.0,
        started: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.delay_seconds = delay_seconds
        self.started = started
        self.release = release
        self.closed = False
        self.close_count = 0

    async def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        if self.closed:
            raise AssertionError("FakeLLMClient was used after aclose.")
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if not self._responses:
            raise AssertionError("FakeLLMClient has no remaining scripted responses.")

        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return item
        return json.dumps(item)

    async def aclose(self) -> None:
        self.closed = True
        self.close_count += 1
