"""Regression coverage for awaited LLM clients and event-loop overlap."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.routes import router
from backend.config import get_settings
from backend.contracts import RecommendRequest
from backend.main import lifespan
from backend.security import require_api_key
from backend.services import CandidateService, RecommendationService
from backend.services.explanations import explain_ranked_trips
from backend.services.feedback import interpret_feedback
from backend.services.llm import (
    AzureOpenAIChatClient,
    LLMConfigurationError,
    OpenAICompatibleClient,
    parse_request,
)
from tests.fake_llm import FakeLLMClient
from tests.test_explanations import ROME_ID, _ranked, _request
from tests.test_feedback import _payload
from tests.test_recommendations import (
    COMPLETE_EXTRACTION,
    RecordingDataService,
    _explain_payload,
    _trip,
)


REFERENCE_DATE = date(2026, 9, 14)
COMPLETE_TEXT = (
    "From ZAG, 21–25 September 2026, under EUR 400, somewhere warm and relaxing."
)
SPU_TEXT = (
    "From SPU, 21–25 September 2026, under EUR 400, somewhere warm and relaxing."
)
SPU_EXTRACTION = {**COMPLETE_EXTRACTION, "origin_iata": "SPU"}
TIMEOUT_BOUND_SECONDS = 5.0


def _tool_response(arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(arguments=arguments)
                        )
                    ]
                )
            )
        ]
    )


class _RecordingAsyncSDK:
    """Stand-in for AsyncAzureOpenAI / AsyncOpenAI used by the live adapters."""

    instances: list["_RecordingAsyncSDK"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.create_calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.gate: asyncio.Event | None = None
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create)
        )
        type(self).instances.append(self)

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_calls.append(kwargs)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if self.gate is not None:
            await self.gate.wait()
        else:
            await asyncio.sleep(0.05)
        self.in_flight -= 1
        return _tool_response(json.dumps(COMPLETE_EXTRACTION))

    async def close(self) -> None:
        self.closed = True


def _run(coro):
    return asyncio.run(coro)


def test_parser_still_returns_validated_complete_request():
    result = _run(
        parse_request(
            COMPLETE_TEXT,
            reference_date=REFERENCE_DATE,
            llm_client=FakeLLMClient([COMPLETE_EXTRACTION]),
        )
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.budget == 400
    assert result.request.currency == "EUR"


def test_timeout_still_retries_then_returns_model_error():
    client = FakeLLMClient([TimeoutError("timed out"), TimeoutError("timed out")])
    result = _run(
        parse_request(
            COMPLETE_TEXT,
            reference_date=REFERENCE_DATE,
            llm_client=client,
        )
    )

    assert result.status == "error"
    assert len(client.calls) == 2
    assert any("twice" in issue for issue in result.issues)


def test_feedback_timeout_still_returns_model_error():
    client = FakeLLMClient([TimeoutError("timed out"), TimeoutError("timed out")])
    result = _run(
        interpret_feedback("Cheaper", _trip(), llm_client=client)
    )

    assert result.status == "error"
    assert len(client.calls) == 2
    assert any("twice" in issue for issue in result.issues)


def test_two_delayed_parse_requests_overlap_and_keep_inputs_separate():
    async def scenario() -> None:
        started_a = asyncio.Event()
        started_b = asyncio.Event()
        release = asyncio.Event()
        task_a = asyncio.create_task(
            parse_request(
                COMPLETE_TEXT,
                reference_date=REFERENCE_DATE,
                llm_client=FakeLLMClient(
                    [COMPLETE_EXTRACTION],
                    started=started_a,
                    release=release,
                ),
            )
        )
        task_b = asyncio.create_task(
            parse_request(
                SPU_TEXT,
                reference_date=REFERENCE_DATE,
                llm_client=FakeLLMClient(
                    [SPU_EXTRACTION],
                    started=started_b,
                    release=release,
                ),
            )
        )
        await asyncio.wait_for(started_a.wait(), timeout=TIMEOUT_BOUND_SECONDS)
        await asyncio.wait_for(started_b.wait(), timeout=TIMEOUT_BOUND_SECONDS)
        assert not task_a.done()
        assert not task_b.done()
        release.set()
        result_a, result_b = await asyncio.wait_for(
            asyncio.gather(task_a, task_b),
            timeout=TIMEOUT_BOUND_SECONDS,
        )
        assert result_a.request is not None
        assert result_b.request is not None
        assert result_a.request.origin == "ZAG"
        assert result_b.request.origin == "SPU"
        assert result_a.request.budget == 400
        assert result_b.request.budget == 400

    _run(scenario())


def test_shared_fake_keeps_concurrent_results_separate():
    class IsolatingFake:
        def __init__(self) -> None:
            self.in_flight = 0
            self.max_in_flight = 0
            self.seen_overlap = asyncio.Event()

        async def complete_function_call(
            self,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            tool_choice: dict[str, Any] | None = None,
        ) -> str:
            text = str(messages[-1]["content"])
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            if self.in_flight >= 2:
                self.seen_overlap.set()
            await asyncio.sleep(0.05)
            self.in_flight -= 1
            payload = SPU_EXTRACTION if "SPU" in text else COMPLETE_EXTRACTION
            return json.dumps(payload)

        async def aclose(self) -> None:
            return None

    async def scenario() -> None:
        client = IsolatingFake()
        task_a = asyncio.create_task(
            parse_request(
                COMPLETE_TEXT,
                reference_date=REFERENCE_DATE,
                llm_client=client,
            )
        )
        task_b = asyncio.create_task(
            parse_request(
                SPU_TEXT,
                reference_date=REFERENCE_DATE,
                llm_client=client,
            )
        )
        await asyncio.wait_for(client.seen_overlap.wait(), timeout=TIMEOUT_BOUND_SECONDS)
        result_a, result_b = await asyncio.wait_for(
            asyncio.gather(task_a, task_b),
            timeout=TIMEOUT_BOUND_SECONDS,
        )
        assert client.max_in_flight >= 2
        assert result_a.request is not None
        assert result_b.request is not None
        assert result_a.request.origin == "ZAG"
        assert result_b.request.origin == "SPU"

    _run(scenario())


def test_health_completes_on_same_loop_while_recommend_llm_is_pending():
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        llm = FakeLLMClient(
            [COMPLETE_EXTRACTION, _explain_payload()],
            started=started,
            release=release,
        )
        service = RecommendationService(
            candidate_service=CandidateService(data_service=RecordingDataService()),  # type: ignore[arg-type]
            llm_client=llm,
        )
        app = FastAPI()
        app.include_router(router)
        app.state.recommendation_service = service
        app.dependency_overrides[require_api_key] = lambda: None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            recommend_task = asyncio.create_task(
                client.post(
                    "/api/recommend",
                    json={"text": COMPLETE_TEXT},
                )
            )
            await asyncio.wait_for(started.wait(), timeout=TIMEOUT_BOUND_SECONDS)
            assert not recommend_task.done()
            health = await asyncio.wait_for(
                client.get("/api/health"),
                timeout=TIMEOUT_BOUND_SECONDS,
            )
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}
            assert not recommend_task.done()
            release.set()
            recommend = await asyncio.wait_for(
                recommend_task,
                timeout=TIMEOUT_BOUND_SECONDS,
            )

        assert recommend.status_code == 200
        body = recommend.json()
        assert body["status"] == "ready"
        assert body["request"]["origin"] == "ZAG"

    _run(scenario())


def test_azure_adapter_reuses_sdk_overlaps_calls_and_closes():
    async def scenario() -> None:
        _RecordingAsyncSDK.instances = []
        wrapper = AzureOpenAIChatClient(
            api_key="azure-test-key",
            azure_endpoint="https://example.openai.azure.com/",
            deployment="chat-deployment",
            api_version="2024-10-21",
        )
        assert _RecordingAsyncSDK.instances == []
        with patch("openai.AsyncAzureOpenAI", _RecordingAsyncSDK):
            first = asyncio.create_task(
                wrapper.complete_function_call(
                    messages=[{"role": "user", "content": COMPLETE_TEXT}],
                    tools=[],
                )
            )
            second = asyncio.create_task(
                wrapper.complete_function_call(
                    messages=[{"role": "user", "content": SPU_TEXT}],
                    tools=[],
                )
            )
            first_payload, second_payload = await asyncio.wait_for(
                asyncio.gather(first, second),
                timeout=TIMEOUT_BOUND_SECONDS,
            )
            await wrapper.aclose()

        assert first_payload
        assert second_payload
        assert len(_RecordingAsyncSDK.instances) == 1
        sdk = _RecordingAsyncSDK.instances[0]
        assert len(sdk.create_calls) == 2
        assert sdk.max_in_flight == 2
        assert sdk.closed is True
        assert sdk.kwargs["azure_endpoint"] == "https://example.openai.azure.com"
        assert sdk.kwargs["api_version"] == "2024-10-21"

    _run(scenario())


def test_openai_compatible_adapter_reuses_sdk_and_closes():
    async def scenario() -> None:
        _RecordingAsyncSDK.instances = []
        wrapper = OpenAICompatibleClient(
            api_key="openai-test-key",
            model="gpt-4o-mini",
            base_url="https://example.invalid/v1",
        )
        assert _RecordingAsyncSDK.instances == []
        with patch("openai.AsyncOpenAI", _RecordingAsyncSDK):
            await wrapper.complete_function_call(
                messages=[{"role": "user", "content": COMPLETE_TEXT}],
                tools=[],
            )
            await wrapper.complete_function_call(
                messages=[{"role": "user", "content": SPU_TEXT}],
                tools=[],
            )
            await wrapper.aclose()

        assert len(_RecordingAsyncSDK.instances) == 1
        sdk = _RecordingAsyncSDK.instances[0]
        assert len(sdk.create_calls) == 2
        assert sdk.closed is True
        assert sdk.kwargs["base_url"] == "https://example.invalid/v1"

    _run(scenario())


def test_lifespan_reuses_injected_client_and_closes_on_shutdown():
    async def scenario() -> None:
        fake = FakeLLMClient([])
        captured: list[Any] = []

        class FakeRepository:
            def __init__(self, settings: Any) -> None:
                self.settings = settings
                self.closed = False
                self.source_name = "test://lifespan"

            async def connect(self) -> None:
                return None

            async def close(self) -> None:
                self.closed = True
                captured.append(self)

        settings = get_settings()
        secret = settings.auth_session_secret or ("test-lifespan-secret-" + "x" * 16)
        patched_settings = replace(
            settings,
            auth_session_secret=secret,
            api_auth_key=settings.api_auth_key or "test-api-key",
        )
        app = FastAPI()
        with (
            patch("backend.main.CosmosDestinationRepository", FakeRepository),
            patch("backend.main.create_llm_client_from_env", return_value=fake),
            patch("backend.main.get_settings", return_value=patched_settings),
        ):
            async with lifespan(app):
                service = app.state.recommendation_service
                assert service._llm_client is fake
                assert service._client() is fake
                assert app.state.llm_client is fake
            assert fake.closed is True
            assert fake.close_count == 1
            assert captured and captured[0].closed is True

    _run(scenario())


def test_lifespan_starts_when_llm_config_is_missing():
    async def scenario() -> None:
        class FakeRepository:
            def __init__(self, settings: Any) -> None:
                self.source_name = "test://lifespan"

            async def connect(self) -> None:
                return None

            async def close(self) -> None:
                return None

        settings = get_settings()
        secret = settings.auth_session_secret or ("test-lifespan-secret-" + "x" * 16)
        patched_settings = replace(
            settings,
            auth_session_secret=secret,
            api_auth_key=settings.api_auth_key or "test-api-key",
        )
        app = FastAPI()
        with (
            patch("backend.main.CosmosDestinationRepository", FakeRepository),
            patch(
                "backend.main.create_llm_client_from_env",
                side_effect=LLMConfigurationError("missing"),
            ),
            patch("backend.main.get_settings", return_value=patched_settings),
        ):
            async with lifespan(app):
                assert app.state.llm_client is None
                assert app.state.recommendation_service._llm_client is None

    _run(scenario())


class _RaisingCloseClient(FakeLLMClient):
    async def aclose(self) -> None:
        await super().aclose()
        raise RuntimeError("llm close failed")


def _lifespan_settings():
    settings = get_settings()
    secret = settings.auth_session_secret or ("test-lifespan-secret-" + "x" * 16)
    return replace(
        settings,
        auth_session_secret=secret,
        api_auth_key=settings.api_auth_key or "test-api-key",
    )


def test_lifespan_closes_repository_when_llm_cleanup_raises():
    async def scenario() -> None:
        fake = _RaisingCloseClient([])
        captured: list[Any] = []

        class FakeRepository:
            def __init__(self, settings: Any) -> None:
                self.closed = False
                self.source_name = "test://lifespan"

            async def connect(self) -> None:
                return None

            async def close(self) -> None:
                self.closed = True
                captured.append(self)

        app = FastAPI()
        with (
            patch("backend.main.CosmosDestinationRepository", FakeRepository),
            patch("backend.main.create_llm_client_from_env", return_value=fake),
            patch("backend.main.get_settings", return_value=_lifespan_settings()),
        ):
            with pytest.raises(RuntimeError, match="llm close failed"):
                async with lifespan(app):
                    assert app.state.llm_client is fake

        assert fake.closed is True
        assert captured and captured[0].closed is True

    _run(scenario())


def test_internally_created_clients_close_on_success_and_failure():
    async def scenario() -> None:
        parse_ok = FakeLLMClient([COMPLETE_EXTRACTION])
        with patch(
            "backend.services.llm.create_llm_client_from_env",
            return_value=parse_ok,
        ):
            parsed = await parse_request(
                COMPLETE_TEXT,
                reference_date=REFERENCE_DATE,
            )
        assert parsed.status == "ready"
        assert parse_ok.closed is True
        assert parse_ok.close_count == 1

        parse_fail = FakeLLMClient([TimeoutError("timed out"), TimeoutError("timed out")])
        with patch(
            "backend.services.llm.create_llm_client_from_env",
            return_value=parse_fail,
        ):
            failed = await parse_request(
                COMPLETE_TEXT,
                reference_date=REFERENCE_DATE,
            )
        assert failed.status == "error"
        assert parse_fail.closed is True
        assert parse_fail.close_count == 1
        assert len(parse_fail.calls) == 2

        explain_ok = FakeLLMClient(
            [
                {
                    "explanations": [
                        {
                            "destination_id": ROME_ID,
                            "evidence_ids": [f"{ROME_ID}::within_budget"],
                        }
                    ]
                }
            ]
        )
        with patch(
            "backend.services.explanations.create_llm_client_from_env",
            return_value=explain_ok,
        ):
            explained = await explain_ranked_trips(
                _request(),
                [_ranked(ROME_ID, "Rome")],
            )
        assert explained.status == "ok"
        assert explain_ok.closed is True

        explain_fail = FakeLLMClient(
            [TimeoutError("timed out"), TimeoutError("timed out")]
        )
        with patch(
            "backend.services.explanations.create_llm_client_from_env",
            return_value=explain_fail,
        ):
            explain_error = await explain_ranked_trips(
                _request(),
                [_ranked(ROME_ID, "Rome")],
            )
        assert explain_error.status == "error"
        assert explain_fail.closed is True
        assert len(explain_fail.calls) == 2

        feedback_ok = FakeLLMClient([_payload(stronger_price_preference=True)])
        with patch(
            "backend.services.feedback.create_llm_client_from_env",
            return_value=feedback_ok,
        ):
            interpreted = await interpret_feedback("Cheaper", _trip())
        assert interpreted.status == "ready"
        assert feedback_ok.closed is True

        feedback_fail = FakeLLMClient(
            [TimeoutError("timed out"), TimeoutError("timed out")]
        )
        with patch(
            "backend.services.feedback.create_llm_client_from_env",
            return_value=feedback_fail,
        ):
            feedback_error = await interpret_feedback("Cheaper", _trip())
        assert feedback_error.status == "error"
        assert feedback_fail.closed is True
        assert len(feedback_fail.calls) == 2

    _run(scenario())


def test_injected_clients_stay_open_after_operations():
    async def scenario() -> None:
        parser = FakeLLMClient([COMPLETE_EXTRACTION])
        parsed = await parse_request(
            COMPLETE_TEXT,
            reference_date=REFERENCE_DATE,
            llm_client=parser,
        )
        assert parsed.status == "ready"
        assert parser.closed is False
        assert parser.close_count == 0

        explainer = FakeLLMClient(
            [
                {
                    "explanations": [
                        {
                            "destination_id": ROME_ID,
                            "evidence_ids": [f"{ROME_ID}::within_budget"],
                        }
                    ]
                }
            ]
        )
        explained = await explain_ranked_trips(
            _request(),
            [_ranked(ROME_ID, "Rome")],
            llm_client=explainer,
        )
        assert explained.status == "ok"
        assert explainer.closed is False

        interpreter = FakeLLMClient([_payload(stronger_price_preference=True)])
        interpreted = await interpret_feedback(
            "Cheaper",
            _trip(),
            llm_client=interpreter,
        )
        assert interpreted.status == "ready"
        assert interpreter.closed is False

    _run(scenario())


def test_retries_do_not_close_owned_or_injected_clients_early():
    async def scenario() -> None:
        owned = FakeLLMClient(["not-json", COMPLETE_EXTRACTION])
        with patch(
            "backend.services.llm.create_llm_client_from_env",
            return_value=owned,
        ):
            parsed = await parse_request(
                COMPLETE_TEXT,
                reference_date=REFERENCE_DATE,
            )
        assert parsed.status == "ready"
        assert len(owned.calls) == 2
        assert owned.close_count == 1
        assert owned.closed is True

        injected = FakeLLMClient(["not-json", COMPLETE_EXTRACTION])
        repaired = await parse_request(
            COMPLETE_TEXT,
            reference_date=REFERENCE_DATE,
            llm_client=injected,
        )
        assert repaired.status == "ready"
        assert len(injected.calls) == 2
        assert injected.closed is False
        assert injected.close_count == 0

    _run(scenario())


def test_recommend_closes_only_internally_created_clients():
    async def scenario() -> None:
        parse_fake = FakeLLMClient([COMPLETE_EXTRACTION])
        explain_fake = FakeLLMClient([_explain_payload()])
        service = RecommendationService(
            candidate_service=CandidateService(data_service=RecordingDataService()),  # type: ignore[arg-type]
        )
        with (
            patch(
                "backend.services.llm.create_llm_client_from_env",
                return_value=parse_fake,
            ),
            patch(
                "backend.services.explanations.create_llm_client_from_env",
                return_value=explain_fake,
            ),
        ):
            result = await service.recommend(
                RecommendRequest(text=COMPLETE_TEXT)
            )
        assert result.status == "ready"
        assert parse_fake.closed is True
        assert explain_fake.closed is True

        injected = FakeLLMClient([COMPLETE_EXTRACTION, _explain_payload()])
        owned_service = RecommendationService(
            candidate_service=CandidateService(data_service=RecordingDataService()),  # type: ignore[arg-type]
            llm_client=injected,
        )
        injected_result = await owned_service.recommend(
            RecommendRequest(text=COMPLETE_TEXT)
        )
        assert injected_result.status == "ready"
        assert injected.closed is False
        assert injected.close_count == 0

    _run(scenario())
