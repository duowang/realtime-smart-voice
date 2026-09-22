import asyncio
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

for module_name in ("pyaudio", "soundfile", "websockets"):
    sys.modules.setdefault(module_name, types.SimpleNamespace())

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda path: None
sys.modules.setdefault("dotenv", dotenv)

for module_name, class_name in (
    ("wake_word_detector", "WakeWordDetector"),
    ("music_commands", "MusicCommandHandler"),
):
    module = types.ModuleType(module_name)
    setattr(module, class_name, object)
    sys.modules.setdefault(module_name, module)

assistant_module = importlib.import_module("realtime_voice_assistant")
DEFAULT_CONFIG_FILE = assistant_module.DEFAULT_CONFIG_FILE
RealtimeVoiceAssistant = assistant_module.RealtimeVoiceAssistant


def test_default_config_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assistant = object.__new__(RealtimeVoiceAssistant)
    config = assistant._load_config(DEFAULT_CONFIG_FILE)

    assert Path(DEFAULT_CONFIG_FILE) == PROJECT_ROOT / "config" / "config.json"
    assert config["realtime_model"] == "gpt-realtime-2.1"


def test_music_pauses_before_wake_greeting_and_conversation():
    assistant = object.__new__(RealtimeVoiceAssistant)
    events = []
    assistant.music_handler = Mock()
    assistant.music_handler.pause_for_conversation = AsyncMock(side_effect=lambda: events.append("pause"))
    assistant.play_wake_word_acknowledgment = AsyncMock(side_effect=lambda: events.append("greeting"))
    assistant.realtime_client = Mock()
    assistant.realtime_client.start_conversation = AsyncMock(side_effect=lambda: events.append("conversation"))
    assistant._log_event = Mock()
    asyncio.run(assistant.handle_wake_word_detection())
    assert events == ["pause", "greeting", "conversation"]


def test_failed_conversation_restores_music():
    assistant = object.__new__(RealtimeVoiceAssistant)
    assistant.music_handler = Mock(pause_for_conversation=AsyncMock())
    assistant.play_wake_word_acknowledgment = AsyncMock()
    assistant.realtime_client = Mock(
        start_conversation=AsyncMock(side_effect=ConnectionError("offline")),
        stop_conversation=AsyncMock(),
    )
    assistant._log_event = Mock()
    asyncio.run(assistant.handle_wake_word_detection())
    assistant.realtime_client.stop_conversation.assert_awaited_once()
