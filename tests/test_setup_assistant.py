import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

import configuration
import setup_assistant as setup
import wake_word_model


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(configuration, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n")
    model = tmp_path / "models" / "custom"
    model.mkdir(parents=True)
    for name in wake_word_model.MODEL_FILES.values():
        (model / name).write_bytes(b"model")
    return tmp_path, {"wake_word_model_dir": "models/custom"}


def test_template_is_private_and_never_overwrites_existing_key(installation, capsys):
    root, _ = installation
    assert setup.create_env_template()
    env = root / ".env"
    assert env.stat().st_mode & 0o777 == 0o600
    env.write_text("OPENAI_API_KEY=private-test-key\n")
    assert not setup.create_env_template()
    assert env.read_text() == "OPENAI_API_KEY=private-test-key\n"
    assert "private-test-key" not in capsys.readouterr().out


def test_template_does_not_follow_a_dangling_symlink(installation):
    root, _ = installation
    target = root / "elsewhere"
    (root / ".env").symlink_to(target)
    assert not setup.create_env_template()
    assert not target.exists()


def test_prepare_needs_no_key_and_respects_custom_model_and_config(
    installation, monkeypatch, capsys
):
    root, config = installation
    download = Mock()
    monkeypatch.setattr(wake_word_model, "ensure_wake_word_model", download)
    assert setup.prepare(config, Path("config/my settings.json")) == 0
    download.assert_called_once_with(root / "models/custom")
    assert (root / ".env").is_file()
    assert "--config 'config/my settings.json'" in capsys.readouterr().out


@pytest.mark.parametrize("source", ["shell", "config"])
def test_configured_key_is_not_shadowed_by_new_template(installation, monkeypatch, capsys, source):
    root, config = installation
    if source == "shell":
        monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    else:
        config["openai_api_key"] = "private-test-key"
    monkeypatch.setattr(wake_word_model, "ensure_wake_word_model", Mock())
    assert setup.prepare(config, root / "config/config.json") == 0
    assert not (root / ".env").exists()
    assert "private-test-key" not in capsys.readouterr().out


def test_doctor_is_offline_and_does_not_create_env_or_open_devices(
    installation, monkeypatch, capsys
):
    import pyaudio
    import pygame
    import requests

    root, config = installation
    forbidden = Mock(side_effect=AssertionError("Doctor must not download or open audio"))
    monkeypatch.setattr(pyaudio, "PyAudio", forbidden)
    monkeypatch.setattr(pygame.mixer, "init", forbidden)
    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(setup.shutil, "which", lambda _: "/mock/ffmpeg")
    before = set(root.rglob("*"))
    assert setup.diagnose(config) == 1
    output = capsys.readouterr().out
    assert output.count("[FIX]") == 1
    assert "[FIX] OpenAI API key" in output
    assert set(root.rglob("*")) == before
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    assert setup.diagnose(config) == 0
    assert "private-test-key" not in capsys.readouterr().out
    forbidden.assert_not_called()


def test_doctor_reports_missing_model_and_ffmpeg(installation, monkeypatch, capsys):
    root, config = installation
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr(setup.shutil, "which", lambda _: None)
    monkeypatch.setattr(setup, "check_dependencies", lambda: True)
    (root / "models/custom" / next(iter(wake_word_model.MODEL_FILES.values()))).write_bytes(b"")
    assert setup.diagnose(config) == 1
    output = capsys.readouterr().out
    assert output.count("[FIX]") == 2
    assert "[FIX] Wake model" in output
    assert "private-test-key" not in output


def test_broken_dependency_has_repair_hint(monkeypatch, capsys):
    monkeypatch.setattr(setup, "DEPENDENCIES", ("pyaudio",))
    monkeypatch.setattr(
        setup.importlib, "import_module", Mock(side_effect=OSError("library missing"))
    )
    assert not setup.check_dependencies()
    assert "system audio libraries" in capsys.readouterr().out


def test_invalid_config_fails_before_download_or_template_creation(installation, monkeypatch):
    root, _ = installation
    path = root / "bad.json"
    path.write_text("not json")
    monkeypatch.setattr(
        setup.sys, "argv", ["setup_assistant.py", "--prepare", "--config", str(path)]
    )
    download = Mock()
    monkeypatch.setattr(wake_word_model, "ensure_wake_word_model", download)
    assert setup.main() == 1
    download.assert_not_called()
    assert not (root / ".env").exists()
    assert "OPENAI_API_KEY" not in os.environ


@pytest.fixture
def wake_settings(installation, monkeypatch):
    import pyaudio
    import requests

    import wake_word_detector

    root, config = installation
    (root / "config").mkdir()
    config.update(wake_keywords=["Hi Taco"], music_volume=0.2, custom_setting={"keep": True})
    (root / "config/config.json").write_text(json.dumps(config))
    model = Mock(return_value={"tokenizer": root / "models/custom/bpe.model"})
    encode = Mock()
    monkeypatch.setattr(wake_word_model, "ensure_wake_word_model", model)
    monkeypatch.setattr(wake_word_detector, "encode_keywords", encode)
    forbidden = Mock(side_effect=AssertionError("Wake settings must not use audio or an API"))
    monkeypatch.setattr(pyaudio, "PyAudio", forbidden)
    monkeypatch.setattr(requests, "get", forbidden)
    return root, config, model, encode


def test_wake_command_creates_personal_config_without_modifying_defaults(
    wake_settings, monkeypatch, capsys
):
    root, config, model, encode = wake_settings
    default = root / "config/config.json"
    original = default.read_bytes()
    monkeypatch.setattr(setup.sys, "argv", ["setup_assistant.py", "--wake-word", "  Hey   Nova "])
    assert setup.main() == 0
    saved = json.loads((root / "config/local.json").read_text())
    assert saved == {**configuration.load_config(default), "wake_keywords": ["Hey Nova"]}
    assert default.read_bytes() == original
    assert not (root / ".env").exists()
    model.assert_called_once_with(root / config["wake_word_model_dir"])
    encode.assert_called_once_with(["Hey Nova"], model.return_value["tokenizer"])
    assert "Next: ./run.sh." in capsys.readouterr().out


def test_wake_command_preserves_existing_personal_settings(wake_settings):
    root, config, _, _ = wake_settings
    local = root / "config/local.json"
    config.update(music_volume=0.15, wake_keywords=["Old", "Aliases"], openai_api_key="test-key")
    local.write_text(json.dumps(config))
    expected = {**configuration.load_config(local), "wake_keywords": ["Hi Taco"]}
    assert setup.set_wake_word("Hi Taco") == 0
    assert json.loads(local.read_text()) == expected


def test_wake_command_updates_only_explicit_custom_config(wake_settings, capsys):
    root, config, _, _ = wake_settings
    custom = root / "config/my settings.json"
    custom.write_text(json.dumps(config))
    original = (root / "config/config.json").read_bytes()
    assert setup.set_wake_word("Hey Nova", custom) == 0
    assert json.loads(custom.read_text())["wake_keywords"] == ["Hey Nova"]
    assert (root / "config/config.json").read_bytes() == original
    assert not (root / "config/local.json").exists()
    assert f"--config '{custom}'" in capsys.readouterr().out


@pytest.mark.parametrize("phrase", ["", "123", "Hey/Nova", "你好"])
def test_invalid_wake_phrase_does_not_download_or_change_settings(wake_settings, phrase):
    root, _, model, encode = wake_settings
    with pytest.raises(ValueError, match="English words"):
        setup.set_wake_word(phrase)
    model.assert_not_called()
    encode.assert_not_called()
    assert not (root / "config/local.json").exists()


def test_unencodable_phrase_preserves_saved_settings(wake_settings):
    root, config, _, encode = wake_settings
    local = root / "config/local.json"
    local.write_text(json.dumps(config))
    original = local.read_bytes()
    encode.side_effect = ValueError("Cannot tokenize wake phrase")
    with pytest.raises(ValueError, match="Cannot tokenize"):
        setup.set_wake_word("Hey Nova")
    assert local.read_bytes() == original


def test_failed_wake_settings_write_preserves_original_and_cleans_temp_file(
    wake_settings, monkeypatch
):
    root, config, _, _ = wake_settings
    local = root / "config/local.json"
    local.write_text(json.dumps(config))
    original = local.read_bytes()
    monkeypatch.setattr(Path, "replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError, match="disk error"):
        setup.set_wake_word("Hey Nova")
    assert local.read_bytes() == original
    assert not list(local.parent.glob(".wake-config-*"))


def test_malformed_personal_settings_are_not_overwritten(wake_settings):
    root, _, model, _ = wake_settings
    local = root / "config/local.json"
    local.write_text("broken json")
    with pytest.raises(ValueError, match="Cannot read configuration"):
        setup.set_wake_word("Hey Nova")
    model.assert_not_called()
    assert local.read_text() == "broken json"
