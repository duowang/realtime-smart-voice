import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

sys.modules.setdefault("pyaudio", types.SimpleNamespace())
sys.modules.setdefault("websockets", types.SimpleNamespace())

if "music_commands" not in sys.modules:
    music_commands = types.ModuleType("music_commands")
    music_commands.MusicCommandHandler = object
    sys.modules["music_commands"] = music_commands

RealtimeVoiceClient = importlib.import_module("realtime_voice_client").RealtimeVoiceClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(RealtimeVoiceClient, "_init_audio", lambda _: None)
    handler = Mock()
    handler.get_status.return_value = {"is_playing": True, "is_paused": True}
    return RealtimeVoiceClient({"openai_api_key": "test-key"}, music_handler=handler)


def test_default_realtime_model_matches_current_generation():
    assert RealtimeVoiceClient.DEFAULT_REALTIME_MODEL == "gpt-realtime-2.1"


def test_calculate_rms_handles_full_scale_pcm16_without_overflow():
    samples = np.array([32767, -32768], dtype=np.int16)

    rms = RealtimeVoiceClient._calculate_rms(samples.tobytes())

    assert rms == pytest.approx(32767.5, abs=0.5)


def test_calculate_rms_returns_zero_for_empty_audio():
    assert RealtimeVoiceClient._calculate_rms(b"") == 0.0


def test_music_start_returns_to_wake_mode_without_requesting_more_speech():
    client = object.__new__(RealtimeVoiceClient)
    client.is_connected = True
    client.conversation_should_end = False
    client._log = Mock()
    client.music_handler = Mock(execute=AsyncMock(return_value={"success": True, "action": "play"}))
    client.stop_conversation = AsyncMock()
    client.websocket = Mock(send=AsyncMock(), recv=AsyncMock(return_value=json.dumps({
        "type": "response.function_call_arguments.done", "name": "play_music",
        "arguments": '{"query":"test"}', "call_id": "test-call",
    })))
    asyncio.run(client._handle_responses())
    assert client.conversation_should_end
    client.stop_conversation.assert_awaited_once()
    events = [json.loads(c.args[0]) for c in client.websocket.send.call_args_list]
    assert [event["type"] for event in events] == ["conversation.item.create"]


def test_realtime_connection_bounds_close_handshake(monkeypatch):
    module = importlib.import_module("realtime_voice_client")
    connect = AsyncMock(return_value=Mock(send=AsyncMock()))
    monkeypatch.setattr(module.websockets, "connect", connect, raising=False)
    client = object.__new__(RealtimeVoiceClient)
    client.config = {}
    client.api_key = "test-key"
    client._build_session_config = Mock(return_value={})
    client._log = Mock()
    asyncio.run(client.initialize())
    assert connect.call_args.kwargs["close_timeout"] == 1


@pytest.mark.parametrize("text", [
    "Stop the music.", "Stop playing.", "Stop.",
    "Please play Bye Bye Bye.", "Pause the music, thanks.",
    "I'm not finished with my question.",
])
def test_music_commands_and_mentions_do_not_end_conversation(client, text):
    assert not client._should_end_conversation(text)


@pytest.mark.parametrize("text", ["Goodbye!", "Thank you.", "Okay, that's all.", "Please end conversation."])
def test_standalone_farewells_still_end_conversation(client, text):
    assert client._should_end_conversation(text)


def test_stop_without_music_ends_conversation(client):
    client.music_handler.get_status.return_value = {"is_playing": False}
    assert client._should_end_conversation("Stop.")


def test_stop_music_transcript_reaches_the_function_handler(client):
    client.is_connected = True
    client.stop_conversation = AsyncMock()

    async def execute(*_):
        client.is_connected = False
        return {"success": True, "action": "stop"}

    client.music_handler.execute = AsyncMock(side_effect=execute)
    client.websocket = Mock(send=AsyncMock(), recv=AsyncMock(side_effect=[
        json.dumps({"type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "Stop the music."}),
        json.dumps({"type": "response.function_call_arguments.done", "name": "stop_music",
                    "arguments": "{}", "call_id": "stop-call"}),
    ]))
    asyncio.run(client._handle_responses())
    client.music_handler.execute.assert_awaited_once_with("stop_music", {})
    client.stop_conversation.assert_not_awaited()
