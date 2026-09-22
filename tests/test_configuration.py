import json

import pytest

from configuration import get_api_key, load_config


@pytest.mark.parametrize(
    "value",
    [
        [],
        None,
        12,
        {"silence_timeout": 0},
        {"conversation_timeout": True},
        {"post_response_timeout": float("nan")},
        {"realtime_model": None},
    ],
)
def test_invalid_config_fails_before_runtime(tmp_path, value):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_config(path)


def test_missing_config_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="Cannot read configuration"):
        load_config(tmp_path / "missing.json")


def test_environment_overrides_config_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    assert get_api_key({"openai_api_key": "config-key"}) == "environment-key"
