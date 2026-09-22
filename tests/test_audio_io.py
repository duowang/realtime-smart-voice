import asyncio
import threading
from unittest.mock import Mock

import pytest

from audio_io import audio_operation, close_stream


def test_cancel_waits_for_native_operation_before_owner_can_close():
    entered, release = threading.Event(), threading.Event()
    events = []

    def read():
        entered.set()
        assert release.wait(2)
        events.append("read finished")

    async def owner():
        try:
            await audio_operation(read)
        finally:
            events.append("closed")

    async def run():
        task = asyncio.create_task(owner())
        while not entered.is_set():
            await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert events == []
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert events == ["read finished", "closed"]

    asyncio.run(run())


def test_close_still_runs_when_stop_fails():
    stream = Mock()
    stream.stop_stream.side_effect = OSError("unplugged")
    close_stream(stream)
    stream.close.assert_called_once()


def test_repeated_cancellation_still_waits_for_audio_worker():
    entered, release = threading.Event(), threading.Event()

    def read():
        entered.set()
        assert release.wait(2)

    async def run():
        task = asyncio.create_task(audio_operation(read))
        while not entered.is_set():
            await asyncio.sleep(0)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
