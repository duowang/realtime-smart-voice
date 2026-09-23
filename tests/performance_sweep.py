"""Repeatable local benchmarks; no microphone, speakers, accounts, or network.

Run with: venv/bin/python tests/performance_sweep.py --output tmp/performance.json
These isolate application overhead, not acoustic or cloud response latency.
"""

import argparse
import asyncio
import contextlib
import io
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from realtime_voice_assistant import RealtimeVoiceAssistant  # noqa: E402
from timers import HISTORY_LIMIT, TimerService  # noqa: E402
from youtube_music_player import YouTubeMusicPlayer  # noqa: E402


async def measure(directory: Path) -> dict:
    service = TimerService(directory / "timers.json", tick=Mock(return_value=False))
    service._timers = {
        str(i): {
            "id": str(i),
            "label": "finished",
            "duration_seconds": 60,
            "deadline_utc": 0,
            "_deadline": 0,
            "state": "dismissed",
            "call_id": "",
        }
        for i in range(HISTORY_LIMIT)
    }
    poll_times = []
    for _ in range(5):
        start = time.perf_counter()
        for _ in range(1000):
            await service.poll()
        poll_times.append((time.perf_counter() - start) * 1000)
    service.tick.reset_mock()
    service.start()
    await asyncio.sleep(1.1)
    await service.close()
    idle_ticks = service.tick.call_count

    assistant = object.__new__(RealtimeVoiceAssistant)
    assistant.timer_alerts = Mock()
    assistant._log_event = Mock()
    cue_times = []
    with patch("realtime_voice_assistant.pyaudio.PyAudio", return_value=Mock()):
        for _ in range(5):
            start = time.perf_counter()
            await assistant.play_wake_cue()
            cue_times.append((time.perf_counter() - start) * 1000)
    assistant._log_event.assert_not_called()

    play_times, result_times = [], []
    mixer = Mock()
    mixer.get_init.return_value = True
    with (
        patch("youtube_music_player.PROJECT_ROOT", directory),
        patch("youtube_music_player.YTMusic"),
        patch("youtube_music_player.pygame.mixer", mixer),
    ):
        player = YouTubeMusicPlayer()
        player.album_art.is_visible = lambda: True

        async def delayed_art(*_):
            await asyncio.sleep(0.2)
            return None

        player.album_art.download = delayed_art
        song_id = player._generate_song_id("12345678901", "Test", "Test")
        Path(player._get_cached_file_path(song_id)).write_bytes(b"mock audio")
        for _ in range(5):
            start = time.perf_counter()
            mixer.music.play.side_effect = lambda start=start: play_times.append(
                (time.perf_counter() - start) * 1000
            )
            assert await player.play_song("12345678901", "Test", "Test", "mock://art")
            result_times.append((time.perf_counter() - start) * 1000)
            await player.stop()
        player.cleanup()

    return {
        "timer_poll_100_history_us": round(statistics.median(poll_times), 2),
        "idle_timer_ticks_in_1_1_seconds": idle_ticks,
        "wake_cue_overhead_ms": round(statistics.median(cue_times), 2),
        "cached_music_start_with_200ms_art_ms": round(statistics.median(play_times), 2),
        "cached_music_result_with_200ms_art_ms": round(statistics.median(result_times), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
        results = asyncio.run(measure(Path(directory)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
