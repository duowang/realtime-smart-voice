import json

import pytest

import configuration
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
        {"timer_alert_volume": True},
        {"timer_alert_volume": 1.1},
        {"timer_alert_seconds": 0},
        {"timer_alert_seconds": 31},
        {"timer_alert_seconds": float("inf")},
        {"timer_store_path": ""},
        {"log_conversation_content": "false"},
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


def test_personal_config_is_automatic_but_explicit_path_wins(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default = config_dir / "config.json"
    default.write_text('{"wake_keywords": ["Hi Taco"]}')
    monkeypatch.setattr(configuration, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(configuration, "DEFAULT_CONFIG_FILE", default)
    assert load_config()["wake_keywords"] == ["Hi Taco"]
    (config_dir / "local.json").write_text('{"wake_keywords": ["Hey Nova"]}')
    assert load_config()["wake_keywords"] == ["Hey Nova"]
    assert load_config(default)["wake_keywords"] == ["Hi Taco"]


def test_broken_personal_config_is_reported_instead_of_silently_using_defaults(
    tmp_path, monkeypatch
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "local.json").write_text("invalid")
    monkeypatch.setattr(configuration, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ValueError, match="local.json"):
        load_config()
