import asyncio
import json
import threading
from unittest.mock import Mock

import pytest

from timers import MAX_ACTIVE, RECOVERY_GRACE, TimerService


class Clock:
    wall = 10000.0
    elapsed = 10.0

    def advance(self, seconds):
        self.wall += seconds
        self.elapsed += seconds


@pytest.fixture
def setup(tmp_path):
    clock, expired, removed = Clock(), Mock(), Mock()
    service = TimerService(
        tmp_path / "timers.json",
        on_expire=expired,
        on_remove=removed,
        wall_clock=lambda: clock.wall,
        clock=lambda: clock.elapsed,
    )
    return service, clock, expired, removed


def test_create_check_expire_dismiss_and_restart(setup):
    service, clock, expired, removed = setup

    async def run():
        result = await service.execute("create_timer", {"duration_seconds": 60, "label": "茶"})
        timer_id = result["timer"]["timer_id"]
        clock.advance(21)
        status = await service.execute("get_timers", {})
        assert status["timers"][0]["remaining_seconds"] == 39
        restored = TimerService(
            service.path, wall_clock=lambda: clock.wall, clock=lambda: clock.elapsed
        )
        assert (await restored.execute("get_timers", {}))["timers"][0]["timer_id"] == timer_id
        clock.advance(39)
        await service.poll()
        await service.poll()
        expired.assert_called_once()
        assert expired.call_args.args[0][0]["label"] == "茶"
        assert expired.call_args.args[0][0]["state"] == "expired"
        result = await service.execute("dismiss_timer", {"timer_id": timer_id})
        assert result["success"] and result["timer"]["state"] == "dismissed"
        removed.assert_called_once_with(timer_id)
        assert not service.has_pending()
        assert not (await service.execute("get_timers", {}))["timers"]
        await service.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        {},
        {"duration_seconds": True},
        {"duration_seconds": 0},
        {"duration_seconds": -1},
        {"duration_seconds": 86401},
        {"duration_seconds": 1.5},
        {"duration_seconds": float("nan")},
        {"duration_seconds": "60"},
        {"duration_seconds": 60, "label": " "},
        {"duration_seconds": 60, "label": 12},
        {"duration_seconds": 60, "label": "tea\x1b[31m"},
        {"duration_seconds": 60, "extra": "x"},
    ],
)
def test_invalid_timer_never_mutates_state(setup, arguments):
    service, *_ = setup
    result = asyncio.run(service.execute("create_timer", arguments))
    assert not result["success"]
    assert not service.has_pending()
    assert not service.path.exists()


def test_same_call_replays_but_new_call_can_create_same_label(setup):
    service, *_ = setup

    async def run():
        arguments = {"duration_seconds": 60, "label": "pasta"}
        one = await service.execute("create_timer", arguments, call_id="a")
        replay = await service.execute("create_timer", arguments, call_id="a")
        two = await service.execute("create_timer", arguments, call_id="b")
        assert one["timer"]["timer_id"] == replay["timer"]["timer_id"]
        assert one["timer"]["timer_id"] != two["timer"]["timer_id"]
        ambiguous = await service.execute("cancel_timer", {"label": "pasta"})
        assert ambiguous["error"] == "ambiguous_timer"
        assert len(ambiguous["timers"]) == 2
        cancelled = await service.execute("cancel_timer", {"timer_id": one["timer"]["timer_id"]})
        assert cancelled["timer"]["state"] == "cancelled"
        # A retransmission must not re-create the cancelled timer.
        assert (await service.execute("create_timer", arguments, call_id="a"))["timer"][
            "state"
        ] == "cancelled"

    asyncio.run(run())


def test_cancel_at_deadline_prevents_alert_and_dismiss_does_not_cancel_countdown(setup):
    service, clock, expired, _ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 10})
        assert not (await service.execute("dismiss_timer", {}))["success"]
        clock.advance(10)
        assert (await service.execute("cancel_timer", {}))["success"]
        await service.poll()
        expired.assert_not_called()

    asyncio.run(run())


def test_recovery_rings_recent_but_marks_old_expiry_missed(setup):
    service, clock, *_ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 10, "label": "old"})
        await service.execute(
            "create_timer", {"duration_seconds": RECOVERY_GRACE + 10, "label": "recent"}
        )
        clock.advance(RECOVERY_GRACE + 11)
        expired = Mock()
        restored = TimerService(
            service.path,
            on_expire=expired,
            wall_clock=lambda: clock.wall,
            clock=lambda: clock.elapsed,
        )
        await restored.poll()
        assert [t["label"] for t in expired.call_args.args[0]] == ["recent"]
        status = await restored.execute("get_timers", {})
        assert {t["label"]: t["state"] for t in status["timers"]} == {
            "old": "missed",
            "recent": "expired",
        }

    asyncio.run(run())


def test_delivered_expiry_does_not_alert_again_after_restart(setup):
    service, clock, expired, _ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 10})
        clock.advance(10)
        await service.poll()
        expired.assert_called_once()
        saved = json.loads(service.path.read_text())
        assert saved["timers"][0]["alert_queued"] is True

        for legacy in (False, True):
            if legacy:
                # Legacy stores lack the marker but already queued expired alerts.
                del saved["timers"][0]["alert_queued"]
                service.path.write_text(json.dumps(saved))
            replay = Mock()
            restored = TimerService(
                service.path,
                on_expire=replay,
                wall_clock=lambda: clock.wall,
                clock=lambda: clock.elapsed,
            )
            await restored.poll()
            replay.assert_not_called()
            assert (await restored.execute("get_timers", {}))["timers"][0]["state"] == "expired"

    asyncio.run(run())


def test_unqueued_expiry_is_retried_after_restart(setup):
    service, clock, *_ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 10})
        clock.advance(10)
        saved = json.loads(service.path.read_text())
        saved["timers"][0]["state"] = "expired"
        service.path.write_text(json.dumps(saved))
        replay = Mock()
        restored = TimerService(
            service.path,
            on_expire=replay,
            wall_clock=lambda: clock.wall,
            clock=lambda: clock.elapsed,
        )
        await restored.poll()
        await restored.poll()
        replay.assert_called_once()
        assert json.loads(service.path.read_text())["timers"][0]["alert_queued"] is True

    asyncio.run(run())


def test_wall_clock_jump_does_not_change_running_countdown(setup):
    service, clock, expired, _ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 60})
        clock.wall += 3600
        await service.poll()
        expired.assert_not_called()
        assert (await service.execute("get_timers", {}))["timers"][0]["remaining_seconds"] == 60
        clock.elapsed += 60
        await service.poll()
        expired.assert_called_once()

    asyncio.run(run())


def test_failed_disk_write_preserves_previous_file_and_memory(setup, monkeypatch):
    service, *_ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 60})
        before = service.path.read_bytes()
        monkeypatch.setattr("timers.os.replace", Mock(side_effect=OSError("disk full")))
        result = await service.execute("create_timer", {"duration_seconds": 10})
        assert result["error"] == "storage_unavailable"
        assert service.path.read_bytes() == before
        assert len((await service.execute("get_timers", {}))["timers"]) == 1
        assert list(service.path.parent.iterdir()) == [service.path]

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["cancel", "expire"])
def test_failed_state_change_preserves_published_records(setup, monkeypatch, operation):
    service, clock, expired, removed = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 1})
        before = service._timers
        saved = service.path.read_bytes()
        monkeypatch.setattr(service, "_write", Mock(side_effect=OSError("disk full")))
        if operation == "expire":
            clock.advance(1)
            with pytest.raises(OSError):
                await service.poll()
        else:
            result = await service.execute("cancel_timer", {})
            assert result["error"] == "storage_unavailable"
        assert service._timers is before
        assert all(t["state"] == "scheduled" for t in before.values())
        assert service.path.read_bytes() == saved
        expired.assert_not_called()
        removed.assert_not_called()

    asyncio.run(run())


def test_scheduler_sleeps_until_change_and_uses_earliest_deadline(setup, monkeypatch):
    service, clock, expired, _ = setup

    async def run():
        waits = asyncio.Queue()

        async def observe_wait(awaitable, timeout):
            waits.put_nowait(timeout)
            await awaitable

        # Observe the scheduler's requested sleep without using wall-clock timing.
        monkeypatch.setattr("timers.asyncio.wait_for", observe_wait)
        async with asyncio.timeout(2):
            service.start()
            assert await waits.get() is None
            await service.execute("create_timer", {"duration_seconds": 60})
            assert await waits.get() == 60
            await service.execute("create_timer", {"duration_seconds": 10})
            assert await waits.get() == 10
            clock.advance(10)
            service.tick = lambda: True  # An alert now needs periodic attention.
            service._changed.set()
            assert await waits.get() == 0.25
            # Expiry is itself a committed change; it may trigger one more tick.
            assert await waits.get() == 0.25
            expired.assert_called_once()
            service.tick = lambda: False
            await service.execute("cancel_timer", {"timer_id": next(iter(service._timers))})
            assert await waits.get() is None
            await service.close()

    asyncio.run(run())


def test_scheduler_wakes_from_idle_and_expires_without_manual_poll(tmp_path):
    async def run():
        expired = asyncio.Event()
        service = TimerService(tmp_path / "timers.json", on_expire=lambda _: expired.set())
        service.start()
        try:
            await asyncio.sleep(0)
            await service.execute("create_timer", {"duration_seconds": 1})
            async with asyncio.timeout(3):
                await expired.wait()
        finally:
            await service.close()
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    asyncio.run(run())


def test_cancelled_caller_still_publishes_committed_timer(setup, monkeypatch):
    service, clock, expired, _ = setup
    entered, release = threading.Event(), threading.Event()
    write = service._write

    def slow_write(records):
        entered.set()
        assert release.wait(2)
        write(records)

    monkeypatch.setattr(service, "_write", slow_write)

    async def run():
        operation = asyncio.create_task(service.execute("create_timer", {"duration_seconds": 1}))
        try:
            while not entered.is_set():
                await asyncio.sleep(0)
            operation.cancel()
            await asyncio.sleep(0)
            assert not operation.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert service.has_pending()
        clock.advance(1)
        await service.poll()
        expired.assert_called_once()

    asyncio.run(run())


def test_scheduler_shutdown_joins_task_and_retains_pending_timer(setup):
    service, *_ = setup

    async def run():
        await service.execute("create_timer", {"duration_seconds": 10})
        service.start()
        task = service._task
        await asyncio.sleep(0)
        await service.close()
        assert task.done()
        assert json.loads(service.path.read_text())["timers"][0]["state"] == "scheduled"
        assert (await service.execute("create_timer", {"duration_seconds": 1}))["error"] == "closed"
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    asyncio.run(run())


@pytest.mark.parametrize(
    "data", ["{", "[]", '{"version": 2, "timers": []}', '{"version": 1, "timers": [{}]}']
)
def test_bad_timer_store_is_not_silently_overwritten(tmp_path, data):
    path = tmp_path / "timers.json"
    path.write_text(data)
    with pytest.raises(ValueError, match="Cannot load timers"):
        TimerService(path)
    assert path.read_text() == data


def test_active_timer_cap(setup):
    service, *_ = setup

    async def run():
        for _ in range(MAX_ACTIVE):
            assert (await service.execute("create_timer", {"duration_seconds": 60}))["success"]
        assert (await service.execute("create_timer", {"duration_seconds": 60}))["error"] == "limit"

    asyncio.run(run())
