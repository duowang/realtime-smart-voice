"""Persistent, application-owned countdowns; no audio or cloud dependencies."""

import asyncio
import json
import logging
import math
import os
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from audio_io import complete_task

logger = logging.getLogger(__name__)
MAX_DURATION = 86400
MAX_ACTIVE = 20
HISTORY_LIMIT = 100
RECOVERY_GRACE = 300
POLL_INTERVAL = 0.25
STATES = {"scheduled", "expired", "cancelled", "dismissed", "missed"}


def _tool(name: str, description: str, properties: dict, required=()) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


SELECTOR = {
    "timer_id": {"type": "string", "description": "ID returned by a timer tool."},
    "label": {"type": "string", "description": "Exact timer label, if its ID is unknown."},
}
TIMER_TOOLS = [
    _tool(
        "create_timer",
        "Start a local countdown. Ask for units if duration is ambiguous.",
        {
            "duration_seconds": {"type": "integer", "minimum": 1, "maximum": MAX_DURATION},
            "label": {"type": "string", "maxLength": 80},
        },
        ("duration_seconds",),
    ),
    _tool(
        "get_timers",
        "Check remaining time and expired/missed timers. Use before selecting an ambiguous timer.",
        {},
    ),
    _tool(
        "cancel_timer",
        "Cancel one countdown or silence one expired timer. Omit selector only if exactly one timer exists.",
        SELECTOR,
    ),
    _tool(
        "dismiss_timer",
        "Acknowledge one expired/missed timer. Does not stop music or cancel a running countdown.",
        SELECTOR,
    ),
]
TIMER_NAMES = {tool["name"] for tool in TIMER_TOOLS}
TIMER_ARGUMENTS = {tool["name"]: set(tool["parameters"]["properties"]) for tool in TIMER_TOOLS}


class TimerService:
    """One scheduler outlives conversations; serialized writes publish atomically.

    Running countdowns use a monotonic clock. UTC is only an estimate for restart
    recovery; this is not an alarm service that wakes a sleeping/stopped machine.
    Cancellation waits for a short disk transaction and its in-memory publication,
    so a committed timer cannot disappear merely because its caller disconnects.
    """

    def __init__(
        self,
        path: Path,
        *,
        on_expire: Callable = lambda _: None,
        on_remove: Callable = lambda _: None,
        tick: Callable[[], bool] = lambda: False,
        wall_clock: Callable = time.time,
        clock: Callable = time.monotonic,
    ):
        self.path = Path(path)
        self.on_expire, self.on_remove, self.tick = on_expire, on_remove, tick
        self.wall_clock, self.clock = wall_clock, clock
        self._lock = asyncio.Lock()
        self._changed = asyncio.Event()
        self._task = None
        self._closed = False
        self._timers = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported timer file version")
            records = data["timers"]
            if not isinstance(records, list) or len(records) > HISTORY_LIMIT:
                raise ValueError("invalid timer records")
            timers = {}
            now, elapsed = self.wall_clock(), self.clock()
            for record in records:
                if (
                    not isinstance(record, dict)
                    or not isinstance(record.get("id"), str)
                    or not record["id"]
                    or record["id"] in timers
                    or not isinstance(record.get("label"), str)
                    or not 1 <= len(record["label"]) <= 80
                    or type(record.get("duration_seconds")) is not int
                    or not 1 <= record["duration_seconds"] <= MAX_DURATION
                    or record.get("state") not in STATES
                    or type(record.get("deadline_utc")) not in (int, float)
                    or not math.isfinite(record["deadline_utc"])
                    or not isinstance(record.get("call_id", ""), str)
                    or type(record.get("alert_queued", False)) is not bool
                ):
                    raise ValueError("invalid timer record")
                record = dict(record)
                # Older stores have no marker. Their expired alerts were
                # already queued during the original expiry tick.
                record.setdefault("alert_queued", record["state"] == "expired")
                remaining = record["deadline_utc"] - now
                if record["state"] == "expired":
                    remaining = min(0, remaining)
                # Retry only an alert that was not queued before the restart.
                if record["state"] == "expired" and record["alert_queued"]:
                    if remaining < -RECOVERY_GRACE:
                        record["state"] = "missed"
                elif record["state"] in {"scheduled", "expired"}:
                    if remaining < -RECOVERY_GRACE:
                        record["state"] = "missed"
                    else:
                        record["state"] = "scheduled"
                record["_deadline"] = elapsed + remaining
                timers[record["id"]] = record
            return timers
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ValueError(f"Cannot load timers from {self.path}: {error}") from error

    def _write(self, records: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "timers": [
                {key: value for key, value in record.items() if not key.startswith("_")}
                for record in records.values()
            ],
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=self.path.parent, encoding="utf-8", delete=False
            ) as output:
                temporary = output.name
                json.dump(data, output, ensure_ascii=False, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    async def _commit(self, records: dict) -> None:
        await asyncio.to_thread(self._write, records)
        self._timers = records
        self._changed.set()

    def _view(self, record: dict) -> dict:
        return {
            "timer_id": record["id"],
            "label": record["label"],
            "duration_seconds": record["duration_seconds"],
            "state": record["state"],
            "remaining_seconds": max(0, math.ceil(record["_deadline"] - self.clock()))
            if record["state"] == "scheduled"
            else 0,
        }

    def has_pending(self) -> bool:
        return any(t["state"] in {"scheduled", "expired"} for t in self._timers.values())

    @staticmethod
    def _result(success: bool, response: str, **details) -> dict:
        return {"success": success, "action": "timer", "response": response, **details}

    async def execute(self, name: str, arguments: dict, *, call_id: str = "") -> dict:
        try:
            # The owned operation publishes state even if a conversation is cancelled.
            return await complete_task(asyncio.create_task(self._execute(name, arguments, call_id)))
        except OSError:
            logger.exception("Timer storage failed")
            return self._result(
                False,
                "I couldn't save that timer change. Please try again.",
                error="storage_unavailable",
            )

    async def _execute(self, name: str, arguments: dict, call_id: str) -> dict:
        async with self._lock:
            if self._closed:
                return self._result(False, "Timers are shutting down.", error="closed")
            if (
                name not in TIMER_ARGUMENTS
                or not isinstance(arguments, dict)
                or set(arguments) - TIMER_ARGUMENTS[name]
            ):
                return self._result(False, "Invalid timer arguments.", error="invalid_arguments")
            if name == "get_timers":
                visible = [
                    self._view(t)
                    for t in self._timers.values()
                    if t["state"] in {"scheduled", "expired", "missed"}
                ]
                return self._result(
                    True, "Here are your timers." if visible else "No timers.", timers=visible
                )
            # Published records are never mutated: copy only entries that change.
            records = self._timers
            if name == "create_timer":
                duration = arguments.get("duration_seconds")
                label = arguments.get("label", "timer")
                if (
                    type(duration) is not int
                    or not 1 <= duration <= MAX_DURATION
                    or not isinstance(label, str)
                    or not 1 <= len(label.strip()) <= 80
                    or not label.strip().isprintable()
                ):
                    return self._result(
                        False,
                        "Use a duration of 1 second to 24 hours and a short label.",
                        error="invalid_arguments",
                    )
                for timer in records.values():
                    if call_id and timer.get("call_id") == call_id:
                        return self._result(
                            True, "This timer request was already saved.", timer=self._view(timer)
                        )
                if (
                    sum(t["state"] in {"scheduled", "expired"} for t in records.values())
                    >= MAX_ACTIVE
                ):
                    return self._result(
                        False, "Cancel or dismiss a timer first (limit 20).", error="limit"
                    )
                timer_id = uuid.uuid4().hex
                timer = {
                    "id": timer_id,
                    "label": label.strip(),
                    "duration_seconds": duration,
                    "deadline_utc": self.wall_clock() + duration,
                    "_deadline": self.clock() + duration,
                    "state": "scheduled",
                    "call_id": call_id,
                    "alert_queued": False,
                }
                records = records | {timer_id: timer}
                while len(records) > HISTORY_LIMIT:
                    old = next(
                        key
                        for key, t in records.items()
                        if t["state"] not in {"scheduled", "expired"}
                    )
                    del records[old]
                await self._commit(records)
                return self._result(True, "Timer set.", timer=self._view(timer))
            if any(not isinstance(v, str) or not v.strip() for v in arguments.values()):
                return self._result(False, "Use a timer ID or label.", error="invalid_arguments")
            states = {"expired", "missed"} if name == "dismiss_timer" else {"scheduled", "expired"}
            candidates = [
                t
                for t in records.values()
                if t["state"] in states
                and (not arguments.get("timer_id") or t["id"] == arguments["timer_id"])
                and (
                    not arguments.get("label")
                    or t["label"].casefold() == arguments["label"].strip().casefold()
                )
            ]
            if not candidates and arguments.get("timer_id") in records:
                previous = records[arguments["timer_id"]]
                if previous["state"] in {"cancelled", "dismissed"}:
                    return self._result(
                        True, f"Timer is already {previous['state']}.", timer=self._view(previous)
                    )
            if len(candidates) != 1:
                return self._result(
                    False,
                    "Which timer?" if candidates else "No matching timer.",
                    error="ambiguous_timer" if candidates else "not_found",
                    timers=[self._view(t) for t in candidates],
                )
            timer = candidates[0]
            timer = timer | {"state": "cancelled" if timer["state"] == "scheduled" else "dismissed"}
            await self._commit(records | {timer["id"]: timer})
            self.on_remove(timer["id"])
            return self._result(True, f"Timer {timer['state']}.", timer=self._view(timer))

    async def poll(self) -> bool:
        """Expose one scheduler tick for deterministic tests without real sleeps."""
        return await complete_task(asyncio.create_task(self._poll()))

    async def _poll(self) -> bool:
        async with self._lock:
            if self._closed:
                return False
            now = self.clock()
            due = [
                t | {"state": "expired", "alert_queued": False}
                for t in self._timers.values()
                if (t["state"] == "scheduled" and t["_deadline"] <= now)
                or (t["state"] == "expired" and not t["alert_queued"])
            ]
            if due:
                await self._commit(self._timers | {t["id"]: t for t in due})
                if not self._closed:
                    self.on_expire([self._view(t) for t in due])
                    await self._commit(
                        self._timers
                        | {t["id"]: t | {"alert_queued": True} for t in due}
                    )
            return bool(self.tick())

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("Timer service is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Sleep until a deadline/change; poll only while a chime needs attention.

        tick returns true for an audible or deferred alert. The event is cleared
        before polling so a concurrent committed change cannot lose its wake-up.
        """
        while True:
            self._changed.clear()
            try:
                needs_tick = await self.poll()
                now = self.clock()
                delay = min(
                    (
                        max(0, t["_deadline"] - now)
                        for t in self._timers.values()
                        if t["state"] == "scheduled"
                    ),
                    default=None,
                )
                if needs_tick:
                    delay = POLL_INTERVAL if delay is None else min(delay, POLL_INTERVAL)
            except Exception:
                # Keep saved timers available after an output or temporary disk failure.
                logger.exception("Timer scheduler tick failed")
                delay = 5
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def close(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        # Wait for an already committing command before the application exits.
        async with self._lock:
            pass
