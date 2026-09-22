import asyncio
import base64
import json
import threading
import time
from unittest.mock import AsyncMock, Mock

import pytest

import realtime_voice_client as module
from realtime_voice_client import RealtimeVoiceClient
from timers import TimerService


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module, "get_api_key", lambda _: "test-key")
    audio = Mock()
    audio.open.return_value.read.return_value = b"\0" * 2048
    monkeypatch.setattr(module.pyaudio, "PyAudio", Mock(return_value=audio))
    handler = Mock(pause_for_conversation=AsyncMock(), resume_after_conversation=AsyncMock())
    handler.get_status.return_value = {"is_playing": True, "is_paused": True}
    return RealtimeVoiceClient({"openai_api_key": "test-key"}, music_handler=handler)


def socket_for(client, monkeypatch, events):
    async def receive():
        if events:
            return json.dumps(events.pop(0))
        await asyncio.Future()

    socket = Mock(send=AsyncMock(), recv=receive, close=AsyncMock())
    monkeypatch.setattr(module.websockets, "connect", AsyncMock(return_value=socket))
    return socket


def test_realtime_connection_waits_for_configuration(client, monkeypatch):
    socket_for(client, monkeypatch, [{"type": "session.created"}, {"type": "session.updated"}])
    asyncio.run(client.initialize())
    assert module.websockets.connect.call_args.kwargs["close_timeout"] == 1
    module.pyaudio.PyAudio.assert_not_called()


def test_invalid_server_session_closes_socket_without_opening_mic(client, monkeypatch):
    socket = socket_for(
        client, monkeypatch, [{"type": "error", "error": {"message": "bad config"}}]
    )
    with pytest.raises(RuntimeError, match="configuration rejected"):
        asyncio.run(client.start_conversation())
    socket.close.assert_awaited_once()
    module.pyaudio.PyAudio.assert_not_called()
    client.music_handler.resume_after_conversation.assert_awaited_once()


@pytest.mark.parametrize(
    "text",
    [
        "Stop the music.",
        "Stop playing.",
        "Stop.",
        "Please play Bye Bye Bye.",
        "Pause the music, thanks.",
        "I'm not finished with my question.",
    ],
)
def test_music_commands_and_mentions_do_not_end_conversation(client, text):
    assert not client._should_end_conversation(text)


@pytest.mark.parametrize(
    "text", ["Goodbye!", "Thank you.", "Okay, that's all.", "Please end conversation."]
)
def test_standalone_farewells_still_end_conversation(client, text):
    assert client._should_end_conversation(text)


def test_stop_without_music_ends_conversation(client):
    client.music_handler.get_status.return_value = {"is_playing": False}
    assert client._should_end_conversation("Stop.")


def tool_response(name, arguments="{}"):
    return {
        "type": "response.done",
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": arguments,
                    "call_id": "call-test",
                }
            ],
        },
    }


def test_stop_music_transcript_reaches_function_handler_once(client):
    client.websocket = Mock(send=AsyncMock())
    client.music_handler.execute = AsyncMock(return_value={"success": True, "action": "stop"})

    async def run():
        await client._handle_event(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "Stop the music.",
            }
        )
        # The earlier arguments event must not trigger a duplicate execution or response.
        await client._handle_event(
            {"type": "response.function_call_arguments.done", "name": "stop_music"}
        )
        client.music_handler.execute.assert_not_awaited()
        await client._handle_event(tool_response("stop_music"))

    asyncio.run(run())
    client.music_handler.execute.assert_awaited_once_with("stop_music", {})
    assert not client.conversation_should_end
    sent = [json.loads(call.args[0])["type"] for call in client.websocket.send.call_args_list]
    assert sent == ["conversation.item.create", "response.create"]


def test_music_start_returns_to_wake_mode_without_more_speech(client):
    client.websocket = Mock(send=AsyncMock())
    client.music_handler.execute = AsyncMock(return_value={"success": True, "action": "play"})
    asyncio.run(client._handle_event(tool_response("play_music", '{"query":"test"}')))
    assert client.conversation_should_end
    assert client._stop_event.is_set()
    assert client.websocket.send.await_count == 1


def test_invalid_function_json_cannot_silently_execute_stop(client):
    client.websocket = Mock(send=AsyncMock())
    client.music_handler.execute = AsyncMock(return_value={"success": False})
    asyncio.run(client._handle_event(tool_response("stop_music", "{")))
    client.music_handler.execute.assert_awaited_once_with("stop_music", None)


def test_timer_tools_route_to_shared_service_and_outlive_conversation(client, tmp_path):
    expired = Mock()
    now = [0.0]
    client.timer_service = TimerService(
        tmp_path / "timers.json", on_expire=expired, clock=lambda: now[0], wall_clock=lambda: now[0]
    )
    client.websocket = Mock(send=AsyncMock(), close=AsyncMock())
    client.music_handler.execute = AsyncMock()

    async def run():
        assert "create_timer" in {
            t["name"] for t in client._build_session_config()["session"]["tools"]
        }
        await client._handle_event(
            tool_response("create_timer", '{"duration_seconds":60,"label":"tea"}')
        )
        assert not client.conversation_should_end
        client.music_handler.execute.assert_not_awaited()
        outputs = [json.loads(c.args[0]) for c in client.websocket.send.call_args_list]
        assert json.loads(outputs[0]["item"]["output"])["timer"]["label"] == "tea"
        assert outputs[-1]["type"] == "response.create"
        # Replaying a completed call cannot create another timer.
        await client._handle_event(
            tool_response("create_timer", '{"duration_seconds":60,"label":"tea"}')
        )
        assert len((await client.timer_service.execute("get_timers", {}))["timers"]) == 1
        await client.stop_conversation()
        now[0] = 60
        await client.timer_service.poll()
        expired.assert_called_once()
        await client.timer_service.close()

    asyncio.run(run())


def test_stop_with_timer_reaches_model_and_speech_hushes_alert(client, tmp_path):
    client.music_handler.get_status.return_value = {"is_playing": False}
    client.timer_service = TimerService(tmp_path / "timers.json")
    client.on_user_activity = Mock()

    async def run():
        await client.timer_service.execute("create_timer", {"duration_seconds": 60})
        assert not client._should_end_conversation("Stop.")
        assert not client._should_end_conversation("Cancel my timer.")
        await client._handle_event({"type": "input_audio_buffer.speech_started"})
        client.on_user_activity.assert_called_once()
        await client.timer_service.close()

    asyncio.run(run())


def test_microphone_failure_cancels_siblings_and_closes_resources(client, monkeypatch):
    socket = socket_for(client, monkeypatch, [{"type": "session.updated"}])
    stream = module.pyaudio.PyAudio.return_value.open.return_value
    stream.read.side_effect = OSError("microphone disconnected")

    async def run():
        with pytest.raises(OSError, match="disconnected"):
            await client.start_conversation()
        assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(run())
    stream.close.assert_called_once()
    socket.close.assert_awaited_once()
    assert client._conversation_task is None
    assert not client.is_connected


def test_cancelled_session_closes_and_can_be_reused(client, monkeypatch):
    sockets = []

    async def run():
        for _ in range(2):
            socket = socket_for(client, monkeypatch, [{"type": "session.updated"}])
            sockets.append(socket)
            task = asyncio.create_task(client.start_conversation())
            while not client.is_connected:
                await asyncio.sleep(0)
            client._assistant_text_buffer = "old response"
            await client.stop_conversation()
            assert task.done()
            assert client._conversation_task is None
        await client.cleanup()
        assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(run())
    assert all(socket.close.await_count == 1 for socket in sockets)
    module.pyaudio.PyAudio.return_value.terminate.assert_called_once()
    client.music_handler.cleanup.assert_not_called()  # Shared player belongs to the assistant.


def test_failed_audio_open_releases_connection(client, monkeypatch):
    socket = socket_for(client, monkeypatch, [{"type": "session.updated"}])
    module.pyaudio.PyAudio.return_value.open.side_effect = OSError("no input device")
    with pytest.raises(OSError, match="input device"):
        asyncio.run(client.start_conversation())
    socket.close.assert_awaited_once()
    assert client.stream is None


def test_failed_response_propagates_instead_of_hanging(client, monkeypatch):
    socket = socket_for(
        client,
        monkeypatch,
        [
            {"type": "session.updated"},
            {"type": "response.done", "response": {"status": "failed", "status_details": "quota"}},
        ],
    )
    with pytest.raises(RuntimeError, match="quota"):
        asyncio.run(asyncio.wait_for(client.start_conversation(), 1))
    socket.close.assert_awaited_once()


def test_barge_in_discards_queued_audio_and_truncates_played_duration(client):
    written, release = threading.Event(), threading.Event()
    client.audio = Mock()
    client.websocket = Mock(send=AsyncMock())

    def write(_):
        written.set()
        assert release.wait(2)

    client.audio.open.return_value.write.side_effect = write

    async def run():
        await client._handle_event(
            {
                "type": "response.output_audio.delta",
                "item_id": "spoken-item",
                "delta": base64.b64encode(b"\0" * 4800).decode(),
            }
        )
        playback = asyncio.create_task(client._play_output())
        try:
            while not written.is_set():
                await asyncio.sleep(0)
            interruption = asyncio.create_task(
                client._handle_event({"type": "input_audio_buffer.speech_started"})
            )
            await asyncio.sleep(0)
            assert client._output_queue.empty()
            release.set()
            await asyncio.wait_for(interruption, 1)
            sent = json.loads(client.websocket.send.call_args.args[0])
            assert sent == {
                "type": "conversation.item.truncate",
                "item_id": "spoken-item",
                "content_index": 0,
                "audio_end_ms": 20,
            }
            assert client.audio.open.return_value.write.call_count == 1
        finally:
            release.set()
            playback.cancel()
            await asyncio.gather(playback, return_exceptions=True)

    asyncio.run(run())


def test_silence_timeout_does_not_interrupt_tool_or_output(client):
    async def run():
        client.config["silence_timeout"] = 0.01
        client.last_user_activity_time = time.monotonic() - 30
        client._tool_in_progress = True
        monitor = asyncio.create_task(client._monitor_silence())
        await asyncio.sleep(0.15)
        assert not client.conversation_should_end
        client._tool_in_progress = False
        await asyncio.wait_for(monitor, 1)
        assert client.conversation_should_end

    asyncio.run(run())


def test_interrupt_before_playback_truncates_new_item_at_zero(client):
    client.websocket = Mock(send=AsyncMock())
    client._played_item = "previous-response"
    client._played_bytes = 96000

    async def run():
        await client._handle_event(
            {
                "type": "response.output_audio.delta",
                "item_id": "new-response",
                "delta": base64.b64encode(b"\0" * 960).decode(),
            }
        )
        await client._interrupt_output()

    asyncio.run(run())
    sent = json.loads(client.websocket.send.call_args.args[0])
    assert sent["item_id"] == "new-response"
    assert sent["audio_end_ms"] == 0


def test_shutdown_does_not_resume_music(client, monkeypatch):
    socket_for(client, monkeypatch, [{"type": "session.updated"}])

    async def run():
        owner = asyncio.create_task(client.start_conversation())
        while not client.is_connected:
            await asyncio.sleep(0)
        await client.stop_conversation(resume_music=False)
        assert owner.done()

    asyncio.run(run())
    client.music_handler.resume_after_conversation.assert_not_awaited()


def test_repeated_cancellation_during_native_read_still_cleans_up(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    socket = socket_for(client, monkeypatch, [{"type": "session.updated"}])
    stream = module.pyaudio.PyAudio.return_value.open.return_value

    def read(*_, **__):
        entered.set()
        assert release.wait(2)
        return b"\0" * 2048

    stream.read.side_effect = read

    async def run():
        owner = asyncio.create_task(client.start_conversation())
        while not entered.is_set():
            await asyncio.sleep(0)
        for _ in range(2):
            owner.cancel()
            await asyncio.sleep(0)
        stream.close.assert_not_called()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await owner
        stream.close.assert_called_once()
        socket.close.assert_awaited_once()
        assert client._conversation_task is None

    asyncio.run(run())
