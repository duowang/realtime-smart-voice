import asyncio
import json
from unittest.mock import AsyncMock, Mock, call

import pytest

import youtube_music_player as player_module
from music_commands import MusicCommandHandler


@pytest.fixture
def player(tmp_path, monkeypatch):
    mixer = Mock()
    mixer.get_init.return_value = True
    mixer.music.get_busy.return_value = True
    monkeypatch.setattr(player_module.pygame, "mixer", mixer)
    monkeypatch.setattr(player_module, "YTMusic", Mock())
    monkeypatch.setattr(player_module, "PROJECT_ROOT", tmp_path)
    result = player_module.YouTubeMusicPlayer()
    result.album_art.is_visible = lambda: False
    return result


@pytest.fixture
def playing(player):
    player.is_playing = True
    player.current_song = {"title": "Test song"}
    return player


def handler_for(player):
    handler = object.__new__(MusicCommandHandler)
    handler.music_player = player
    handler.log_function = None
    return handler


def test_explicit_pause_overrides_conversation_auto_resume(playing):
    handler = handler_for(playing)
    assert asyncio.run(handler.pause_for_conversation())
    assert playing.was_paused_for_conversation
    result = asyncio.run(handler.execute("pause_music", {}))
    assert result["success"] and result["action"] == "pause"
    assert playing.is_paused
    assert not asyncio.run(handler.resume_after_conversation())
    player_module.pygame.mixer.music.unpause.assert_not_called()
    assert asyncio.run(handler.execute("resume_music", {}))["success"]
    assert not playing.is_paused


def test_regular_conversation_pause_resumes_once(playing):
    assert asyncio.run(playing.pause_for_conversation())
    assert asyncio.run(playing.resume_after_conversation())
    assert not asyncio.run(playing.resume_after_conversation())
    player_module.pygame.mixer.music.unpause.assert_called_once()


def test_user_paused_track_stays_paused_across_another_conversation(playing):
    assert asyncio.run(playing.pause())
    assert not asyncio.run(playing.pause_for_conversation())
    assert not asyncio.run(playing.resume_after_conversation())
    player_module.pygame.mixer.music.get_busy.return_value = False
    assert playing.get_status()["is_paused"]
    assert playing.get_status()["is_playing"]


def cache_track(player, video="12345678901", title="Test song"):
    path = player_module.Path(
        player._get_cached_file_path(player._generate_song_id(video, title, "Test"))
    )
    path.write_bytes(b"fake mp3")
    return path


def test_play_reports_success_only_after_load_and_sets_volume(player):
    path = cache_track(player)
    assert asyncio.run(player.play_song("12345678901", "Test song", "Test"))
    calls = player_module.pygame.mixer.music.mock_calls
    assert calls[-3:] == [call.load(str(path)), call.set_volume(player.DEFAULT_VOLUME), call.play()]
    assert player.get_status()["is_playing"]
    assert next(iter(player._load_metadata().values()))["play_count"] == 1


def test_failed_mixer_load_does_not_report_success_or_cache_a_play(player):
    cache_track(player)
    player_module.pygame.mixer.music.load.side_effect = OSError("corrupt track")
    assert not asyncio.run(player.play_song("12345678901", "Test song", "Test"))
    assert player.get_status() == {"is_playing": False, "is_paused": False, "current_song": None}
    assert player._load_metadata() == {}


def test_finished_track_clears_state(playing):
    player_module.pygame.mixer.music.get_busy.return_value = False
    assert not playing.get_status()["is_playing"]
    assert playing.current_song is None
    assert not asyncio.run(playing.pause_for_conversation())


@pytest.mark.parametrize("during", ["search", "download"])
def test_stop_invalidates_inflight_work(player, during):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(*_, **__):
            entered.set()
            await release.wait()
            if during == "search":
                return [
                    {"videoId": "12345678901", "title": "Test", "artist": "Test", "thumbnail": None}
                ]
            return True

        if during == "search":
            player.search_songs = delayed
            work = asyncio.create_task(player.play_search_result("Test"))
        else:
            player._download_song = delayed
            work = asyncio.create_task(player.play_song("12345678901"))
        await entered.wait()
        await player.stop()
        release.set()
        assert not await work
        player_module.pygame.mixer.music.play.assert_not_called()
        assert not player.get_status()["is_playing"]

    asyncio.run(run())


def test_cancelled_download_never_starts_playback(player):
    async def run():
        entered = asyncio.Event()

        async def download(*_):
            entered.set()
            await asyncio.Future()

        player._download_song = download
        task = asyncio.create_task(player.play_song("12345678901"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not player.get_status()["is_playing"]
        player_module.pygame.mixer.music.play.assert_not_called()

    asyncio.run(run())


def test_stop_paused_music_prevents_later_auto_resume(playing):
    asyncio.run(playing.pause_for_conversation())
    assert asyncio.run(playing.stop())
    assert not asyncio.run(playing.resume_after_conversation())
    assert playing.current_song is None
    assert not playing.is_paused
    player_module.pygame.mixer.music.unload.assert_called_once()


def test_cleanup_is_idempotent_and_discards_pause_state(playing):
    asyncio.run(playing.pause_for_conversation())
    playing.cleanup()
    playing.cleanup()
    player_module.pygame.mixer.quit.assert_called_once()
    assert not playing.was_paused_for_conversation
    assert not asyncio.run(playing.play_song("12345678901"))


@pytest.mark.parametrize("volume", [-0.1, 1.1, float("nan")])
def test_invalid_volume_rejected_before_hardware_or_network(player, volume, monkeypatch):
    api = Mock()
    monkeypatch.setattr(player_module, "YTMusic", api)
    with pytest.raises(ValueError, match="music_volume"):
        player_module.YouTubeMusicPlayer(volume=volume)
    api.assert_not_called()


@pytest.mark.parametrize("arguments", [[], None, {"query": 5}, {"query": "  "}, {}])
def test_invalid_play_arguments_never_search(player, arguments):
    player.play_search_result = AsyncMock()
    result = asyncio.run(handler_for(player).execute("play_music", arguments))
    assert not result["success"]
    player.play_search_result.assert_not_awaited()


def test_cache_metadata_failure_preserves_existing_file(player, monkeypatch):
    player._save_metadata({"123456789abc": {"title": "old"}})
    monkeypatch.setattr(player_module.json, "dump", Mock(side_effect=OSError("disk full")))
    player._save_metadata({"new": {}})
    assert json.loads(player_module.Path(player.metadata_file).read_text()) == {
        "123456789abc": {"title": "old"}
    }
    assert len(list(player_module.Path(player.cache_dir).iterdir())) == 1


def test_cache_drops_invalid_metadata_paths(player):
    player_module.Path(player.metadata_file).write_text(
        '{"../../outside": {}, "123456789abc": [], "abcdefabcdef": {}}'
    )
    assert player._load_metadata() == {"abcdefabcdef": {}}


def test_download_publishes_complete_audio_and_removes_staging(player, monkeypatch):
    destination = player_module.Path(player.cache_dir) / "complete.mp3"
    options = []

    class Downloader:
        def __init__(self, configuration):
            options.append(configuration)
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def download(self, urls):
            assert urls == ["https://music.youtube.com/watch?v=12345678901"]
            assert not destination.exists()
            output = player_module.Path(self.configuration["outtmpl"] % {"ext": "mp3"})
            output.write_bytes(b"complete download")

    monkeypatch.setattr(player_module.yt_dlp, "YoutubeDL", Downloader)
    assert asyncio.run(player._download_song("12345678901", str(destination)))
    assert destination.read_bytes() == b"complete download"
    assert list(player_module.Path(player.cache_dir).iterdir()) == [destination]
    assert options[0]["noplaylist"]


def test_failed_download_preserves_previous_audio(player, monkeypatch):
    destination = player_module.Path(player.cache_dir) / "complete.mp3"
    destination.write_bytes(b"previous valid track")
    monkeypatch.setattr(player_module.yt_dlp, "YoutubeDL", Mock(side_effect=OSError("offline")))
    assert not asyncio.run(player._download_song("12345678901", str(destination)))
    assert destination.read_bytes() == b"previous valid track"
    assert list(player_module.Path(player.cache_dir).iterdir()) == [destination]
