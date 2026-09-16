from __future__ import annotations

import pytest

from backend.services.llm import (
    AzureOpenAIChatClient,
    LLMConfigurationError,
    OpenAICompatibleClient,
    create_llm_client_from_env,
)

AZURE_ENV_NAMES = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


def _clear_llm_env(monkeypatch) -> None:
    for name in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "OPENAI_MODEL",
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "LLM_API_VERSION",
        *AZURE_ENV_NAMES,
    ):
        monkeypatch.delenv(name, raising=False)


def test_env_file_is_loaded_without_overriding_process_values(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_API_KEY=from-file-key\nLLM_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.services.llm._ENV_PATH", env_file)
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "process-model")

    client = create_llm_client_from_env()

    assert isinstance(client, OpenAICompatibleClient)
    assert client._api_key == "from-file-key"
    assert client._model == "process-model"


def test_placeholder_api_key_is_rejected(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=replace-with-your-key\n", encoding="utf-8")
    monkeypatch.setattr("backend.services.llm._ENV_PATH", env_file)
    _clear_llm_env(monkeypatch)

    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY or OPENAI_API_KEY"):
        create_llm_client_from_env()


def test_azure_chat_settings_use_azure_client(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AZURE_OPENAI_ENDPOINT=https://example.openai.azure.com/",
                "AZURE_OPENAI_API_KEY=azure-test-key",
                "AZURE_OPENAI_DEPLOYMENT=chat-deployment",
                "AZURE_OPENAI_API_VERSION=2024-10-21",
                "LLM_API_KEY=other-service-key",
                "LLM_MODEL=gpt-4o-mini",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.services.llm._ENV_PATH", env_file)
    _clear_llm_env(monkeypatch)

    client = create_llm_client_from_env()

    assert isinstance(client, AzureOpenAIChatClient)
    assert client.client_kind == "azure_openai"
    assert client._model == "chat-deployment"
    assert client._azure_endpoint == "https://example.openai.azure.com"


def test_partial_azure_config_does_not_fall_back_to_public_openai(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AZURE_OPENAI_ENDPOINT=https://example.openai.azure.com/\n"
        "LLM_API_KEY=other-service-key\n"
        "LLM_MODEL=gpt-4o-mini\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("backend.services.llm._ENV_PATH", env_file)
    _clear_llm_env(monkeypatch)

    with pytest.raises(LLMConfigurationError, match="Incomplete Academy Azure"):
        create_llm_client_from_env()
