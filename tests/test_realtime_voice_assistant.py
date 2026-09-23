import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

import realtime_voice_assistant as module
from configuration import DEFAULT_CONFIG_FILE, PROJECT_ROOT, load_config
from realtime_voice_assistant import RealtimeVoiceAssistant


@pytest.fixture
def assistant():
    result = object.__new__(RealtimeVoiceAssistant)
    result.config = {"conversation_timeout": 1}
    result._api_key = "test-key"
    result._shutting_down = False
    result._cleaned_up = False
    result.timer_service = Mock(close=AsyncMock())
    result.timer_alerts = Mock()
    result._pending_timer_alerts = {}
    result._playing_prompt = False
    result.music_handler = Mock(pause_for_conversation=AsyncMock(), aclose=AsyncMock())
    result.play_wake_word_acknowledgment = AsyncMock()
    result.realtime_client = Mock(
        start_conversation=AsyncMock(), stop_conversation=AsyncMock(), cleanup=AsyncMock()
    )
    result.wake_word_detector = Mock()
    result._log_event = Mock()
    result._close_logging = Mock()
    return result


def test_default_config_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Path(DEFAULT_CONFIG_FILE) == PROJECT_ROOT / "config" / "config.json"
    assert load_config()["realtime_model"] == "gpt-realtime-2.1"


def test_music_pauses_before_wake_greeting_and_conversation(assistant):
    events = []
    assistant.timer_alerts.hush.side_effect = lambda: events.append("hush")
    assistant.music_handler.pause_for_conversation.side_effect = lambda: events.append("pause")
    assistant.play_wake_word_acknowledgment.side_effect = lambda: events.append("greeting")
    assistant.realtime_client.start_conversation.side_effect = lambda: events.append("conversation")
    asyncio.run(assistant.handle_wake_word_detection())
    assert events == ["hush", "pause", "greeting", "conversation"]


def test_failed_conversation_restores_music(assistant):
    assistant.realtime_client.start_conversation.side_effect = ConnectionError("offline")
    asyncio.run(assistant.handle_wake_word_detection())
    assistant.realtime_client.stop_conversation.assert_awaited_once_with(resume_music=True)


def test_timer_labels_cannot_emit_terminal_controls(assistant, capsys):
    assistant._queue_timer_alerts([{"timer_id": "a", "label": "tea\x1b]52;c;payload\x07"}])
    output = capsys.readouterr().out
    assert "Timer finished: tea" in output
    assert "\x1b" not in output and "\x07" not in output


def test_assistant_log_boundary_omits_music_content_and_redacts_errors(assistant):
    assistant.logger = Mock()
    RealtimeVoiceAssistant._log_event(assistant, "MUSIC_SEARCH", "private query")
    assistant.logger.info.assert_called_with("%s: %s", "MUSIC_SEARCH", "[content omitted]")
    RealtimeVoiceAssistant._log_event(assistant, "CONVERSATION_ERROR", "key=test-key\x1b[31m")
    assistant.logger.info.assert_called_with("%s: %s", "CONVERSATION_ERROR", "key=[REDACTED][31m")


def test_timeout_covers_the_active_conversation(assistant):
    cancelled = []

    async def forever():
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    assistant.config["conversation_timeout"] = 0.01
    assistant.realtime_client.start_conversation.side_effect = forever
    asyncio.run(asyncio.wait_for(assistant.handle_wake_word_detection(), 1))
    assert cancelled == [True]
    assistant.realtime_client.stop_conversation.assert_awaited_once()


def test_failed_greeting_write_releases_every_resource(assistant, monkeypatch):
    audio = Mock()
    audio.open.return_value.write.side_effect = OSError("speaker unplugged")
    monkeypatch.setattr(module.pyaudio, "PyAudio", Mock(return_value=audio))
    monkeypatch.setattr(
        module.sf, "read", Mock(return_value=(np.zeros((4, 1), dtype=np.float32), 24000))
    )
    asyncio.run(assistant._play_audio_file("unused.wav", "greeting", "GREETING"))
    audio.open.return_value.close.assert_called_once()
    audio.terminate.assert_called_once()


def test_greeting_drain_keeps_loop_responsive_and_finishes_before_termination(
    assistant, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    audio = Mock()

    def drain():
        entered.set()
        assert release.wait(2)

    audio.open.return_value.stop_stream.side_effect = drain
    monkeypatch.setattr(module.pyaudio, "PyAudio", Mock(return_value=audio))
    monkeypatch.setattr(
        module.sf, "read", Mock(return_value=(np.zeros((4, 1), dtype=np.float32), 24000))
    )

    async def run():
        task = asyncio.create_task(assistant._play_audio_file("unused.wav", "hi", "HI"))
        try:
            async with asyncio.timeout(1):
                while not entered.is_set():
                    await asyncio.sleep(0)
            assert assistant._playing_prompt
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
            audio.terminate.assert_not_called()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not assistant._playing_prompt
        audio.open.return_value.close.assert_called_once()
        audio.terminate.assert_called_once()

    asyncio.run(run())


def test_cleanup_continues_after_component_failure(assistant):
    assistant.realtime_client.cleanup.side_effect = OSError("failed cleanup")
    with pytest.raises(OSError):
        asyncio.run(assistant.cleanup())
    assistant.wake_word_detector.cleanup.assert_called_once()
    assistant.music_handler.aclose.assert_awaited_once()
    assistant._close_logging.assert_called_once()
    assistant.timer_service.close.assert_awaited_once()
    assistant.timer_alerts.hush.assert_called_once()
    asyncio.run(assistant.cleanup())
    assistant.music_handler.aclose.assert_awaited_once()


def test_timer_alert_waits_for_speech_and_cancel_removes_pending_alert(assistant):
    client = assistant.realtime_client
    client.is_connected = True
    client._user_speaking = True
    client._response_in_progress = False
    client.is_assistant_speaking = False
    client._output_queue = asyncio.Queue()
    assistant._queue_timer_alerts([{"timer_id": "a", "label": "tea"}])
    assert assistant._tick_timer_alerts()  # Keep ticking while the alert is deferred.
    assistant.timer_alerts.ring.assert_not_called()
    client._user_speaking = False
    assistant._tick_timer_alerts()
    assistant.timer_alerts.ring.assert_called_once_with([{"timer_id": "a", "label": "tea"}])
    assistant._queue_timer_alerts([{"timer_id": "b", "label": "pasta"}])
    assistant._remove_timer_alert("b")
    assert not assistant._pending_timer_alerts


def test_timer_scheduler_can_sleep_once_alerts_are_idle(assistant):
    assistant.realtime_client.is_connected = False
    assistant.timer_alerts.is_ringing = True
    assert assistant._tick_timer_alerts()
    assistant.timer_alerts.is_ringing = False
    assert not assistant._tick_timer_alerts()


def test_closed_conversation_cannot_suppress_new_timer_alerts(assistant):
    # A timeout can close the socket before response.done clears these flags.
    assistant.realtime_client.is_connected = False
    assistant.realtime_client._response_in_progress = True
    assistant.realtime_client._user_speaking = True
    assistant._queue_timer_alerts([{"timer_id": "a", "label": "tea"}])
    assistant._tick_timer_alerts()
    assistant.timer_alerts.ring.assert_called_once()


def test_timer_cleanup_failure_still_releases_voice_and_music(assistant):
    assistant.timer_service.close.side_effect = OSError("timer failure")
    with pytest.raises(OSError, match="timer failure"):
        asyncio.run(assistant.cleanup())
    assistant.timer_alerts.hush.assert_called_once()
    assistant.realtime_client.cleanup.assert_awaited_once()
    assistant.music_handler.aclose.assert_awaited_once()


def test_partial_initialization_releases_music(monkeypatch):
    monkeypatch.setattr(module, "get_api_key", lambda _: "test")
    monkeypatch.setattr(RealtimeVoiceAssistant, "_setup_logging", lambda _: None)
    close_logging = Mock()
    monkeypatch.setattr(RealtimeVoiceAssistant, "_close_logging", close_logging)
    handler = Mock()
    monkeypatch.setattr(module, "MusicCommandHandler", Mock(return_value=handler))
    monkeypatch.setattr(module, "RealtimeVoiceClient", Mock())
    monkeypatch.setattr(module, "WakeWordDetector", Mock(side_effect=OSError("no mic")))
    with pytest.raises(OSError):
        RealtimeVoiceAssistant()
    handler.cleanup.assert_called_once()
    close_logging.assert_called_once()
