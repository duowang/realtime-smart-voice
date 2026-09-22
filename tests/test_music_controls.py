import asyncio
import importlib.util
import sys
import threading
from pathlib import Path
from unittest.mock import Mock, call

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def music_modules(monkeypatch):
    pygame = Mock()
    monkeypatch.setitem(sys.modules, "pygame", pygame)
    monkeypatch.setitem(sys.modules, "yt_dlp", Mock())
    monkeypatch.setitem(sys.modules, "ytmusicapi", Mock())
    spec = importlib.util.spec_from_file_location("youtube_music_player", SRC_DIR / "youtube_music_player.py")
    player_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(player_module)
    monkeypatch.setitem(sys.modules, "youtube_music_player", player_module)
    spec = importlib.util.spec_from_file_location("tested_music_commands", SRC_DIR / "music_commands.py")
    commands_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(commands_module)
    return player_module, commands_module, pygame


@pytest.fixture
def player(music_modules):
    player_module, _, _ = music_modules
    player = object.__new__(player_module.YouTubeMusicPlayer)
    player._playback_lock = threading.Lock()
    player.is_playing = True
    player.is_paused = False
    player.was_paused_for_conversation = False
    player.current_song = {"title": "Test song"}
    player.volume = player.DEFAULT_VOLUME
    player._log = Mock()
    return player


def test_explicit_pause_overrides_conversation_auto_resume(player, music_modules):
    _, commands, pygame = music_modules
    handler = object.__new__(commands.MusicCommandHandler)
    handler.music_player = player
    handler.log_function = None

    assert asyncio.run(handler.pause_for_conversation())
    pygame.mixer.music.pause.assert_called_once()
    assert player.was_paused_for_conversation

    result = asyncio.run(handler.execute("pause_music", {}))
    assert result["success"]
    assert result["action"] == "pause"
    assert player.is_paused
    assert not asyncio.run(handler.resume_after_conversation())
    pygame.mixer.music.unpause.assert_not_called()

    assert asyncio.run(handler.execute("resume_music", {}))["success"]
    pygame.mixer.music.unpause.assert_called_once()
    assert not player.is_paused


def test_regular_conversation_pause_resumes_once(player, music_modules):
    _, _, pygame = music_modules
    assert asyncio.run(player.pause_for_conversation())
    assert asyncio.run(player.resume_after_conversation())
    assert not asyncio.run(player.resume_after_conversation())
    pygame.mixer.music.unpause.assert_called_once()


def test_user_paused_track_stays_paused_across_another_conversation(player):
    assert asyncio.run(player.pause())
    assert not asyncio.run(player.pause_for_conversation())
    assert not asyncio.run(player.resume_after_conversation())
    assert player.is_paused


def test_playback_monitor_preserves_paused_track_and_sets_volume_after_load(
    player, music_modules, tmp_path, monkeypatch,
):
    module, _, pygame = music_modules
    path = tmp_path / "track.mp3"
    path.touch()
    player.is_paused = True
    player.was_paused_for_conversation = True
    pygame.mixer.music.get_busy.return_value = False
    pauses = []

    def paused_tick(_):
        # Paused music is not busy in pygame, but must retain its track/state.
        assert player.is_playing
        assert player.current_song["title"] == "Test song"
        pauses.append(player.is_paused)
        asyncio.run(player.resume_after_conversation())

    monkeypatch.setattr(module.time, "sleep", paused_tick)
    player._play_cached_audio(str(path), "Test song")
    assert pauses == [True]
    assert pygame.mixer.music.mock_calls[:4] == [
        call.load(str(path)), call.set_volume(player.DEFAULT_VOLUME), call.play(), call.pause(),
    ]
    assert not player.is_playing
    assert player.current_song is None


@pytest.mark.parametrize("volume", [-0.1, 1.1, float("nan")])
def test_invalid_volume_rejected_before_hardware_or_network(music_modules, volume):
    module, _, pygame = music_modules
    with pytest.raises(ValueError, match="music_volume"):
        module.YouTubeMusicPlayer(volume=volume)
    pygame.mixer.init.assert_not_called()
