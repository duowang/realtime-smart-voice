import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

import timer_alerts as module
from timer_alerts import TimerAlerts


@pytest.fixture
def alerts(monkeypatch):
    mixer = Mock()
    mixer.get_init.return_value = (44100, -16, 2)
    monkeypatch.setattr(module.pygame, "mixer", mixer)
    return TimerAlerts(Mock()), mixer


def test_chime_uses_bounded_separate_channel_and_restores_volume(alerts):
    player, mixer = alerts
    player.ring([{"timer_id": "one"}, {"timer_id": "two"}])
    channel = mixer.Sound.return_value.play.return_value
    mixer.Sound.return_value.play.assert_called_once_with(loops=-1, maxtime=10000)
    player.duck_music.assert_called_with(True)
    player.remove("one")
    channel.stop.assert_not_called()
    player.remove("two")
    channel.stop.assert_called_once()
    player.duck_music.assert_called_with(False)
    mixer.music.pause.assert_not_called()
    mixer.music.unpause.assert_not_called()


def test_natural_alert_end_releases_ducking(alerts):
    player, mixer = alerts
    player.ring([{"timer_id": "one"}])
    mixer.Sound.return_value.play.return_value.get_busy.return_value = False
    player.update()
    assert player._channel is None
    player.duck_music.assert_called_with(False)


def test_no_channel_does_not_leave_music_ducked(alerts):
    player, mixer = alerts
    mixer.Sound.return_value.play.return_value = None
    with pytest.raises(RuntimeError, match="channel"):
        player.ring([{"timer_id": "one"}])
    player.duck_music.assert_called_with(False)


def test_real_sdl_dummy_mixer_plays_and_stops_chime(tmp_path):
    """Exercise real PCM generation/SDL mixing in a process with no audio device."""
    root = Path(__file__).resolve().parents[1]
    script = """
import asyncio
import pygame
from timer_alerts import TimerAlerts
from timers import TimerService
from youtube_music_player import YouTubeMusicPlayer
from pathlib import Path
import sys

async def run():
    now = [100.0]
    player = YouTubeMusicPlayer()
    alerts = TimerAlerts(player.set_alert_ducked, duration=1)
    service = TimerService(Path(sys.argv[1]), on_expire=alerts.ring,
                           on_remove=alerts.remove, tick=alerts.update,
                           wall_clock=lambda: now[0], clock=lambda: now[0])
    try:
        result = await service.execute('create_timer', {'duration_seconds': 1})
        now[0] += 1
        await service.poll()
        assert alerts._channel.get_busy()
        assert player._alert_ducked
        assert pygame.mixer.music.get_volume() < player.volume
        await service.execute('dismiss_timer', {'timer_id': result['timer']['timer_id']})
        assert alerts._channel is None
        assert not player._alert_ducked
        assert not pygame.mixer.get_busy()
    finally:
        await service.close()
        alerts.hush()
        player.cleanup()
    assert not pygame.mixer.get_init()

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "timers.json")],
        env={
            **os.environ,
            "SDL_AUDIODRIVER": "dummy",
            "PYGAME_HIDE_SUPPORT_PROMPT": "1",
            "PYTHONPATH": str(root / "src"),
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
