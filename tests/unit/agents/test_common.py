from __future__ import annotations

from agens_novel.agents.common import load_agent_settings
from agens_novel.llm.runtime_context import RuntimeModelConfig, model_runtime


def test_load_agent_settings_keeps_runtime_provider_transport_outside_key_state() -> None:
    runtime = RuntimeModelConfig(
        provider="deepseek",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        api_key="test-only-key",
        source="evaluation",
        provider_transport="json_object",
    )

    with model_runtime(runtime):
        settings = load_agent_settings("world_builder")

    assert settings["provider"] == "deepseek"
    assert settings["provider_transport"] == "json_object"
    assert settings["model"] == "deepseek-v4-flash"
    assert settings["api_key_set"] is True
    assert "api_key" not in settings
