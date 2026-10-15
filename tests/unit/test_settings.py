from codepilot.config.settings import Settings


def test_redacted_snapshot_does_not_contain_api_key() -> None:
    settings = Settings.model_validate(
        {
            "llm_model": "deepseek-test",
            "llm_base_url": "https://api.deepseek.example/v1",
            "llm_api_key": "super-secret",
        }
    )

    snapshot = settings.redacted_snapshot()

    assert snapshot["base_url_identifier"] == "api.deepseek.example"
    assert "super-secret" not in repr(snapshot)
    assert "llm_api_key" not in snapshot
    assert snapshot["llm_request_retries"] == 2
    assert snapshot["agent_max_retries"] == 1
    assert snapshot["tool_policy_version"] == "mvp-v1"
