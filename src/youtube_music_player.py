"""Search, cache and control one YouTube Music track through pygame's mixer."""

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import pygame
import yt_dlp
from ytmusicapi import YTMusic

from album_art import AlbumArt
from configuration import PROJECT_ROOT
from diagnostics import log_message

logger = logging.getLogger(__name__)
MAX_SONG_BYTES = 200 * 1024 * 1024
MAX_SONG_SECONDS = 2 * 60 * 60


class YouTubeMusicPlayer:
    """Pygame owns playback; all application state stays on the asyncio thread.

    A generation invalidates pending downloads when stop or another play wins.
    Worker threads only fetch files and never change playback state.
    """

    DEFAULT_VOLUME = 0.35

    def __init__(self, log_function=None, volume: float | None = None):
        self.log_function = log_function
        self.volume = float(self.DEFAULT_VOLUME if volume is None else volume)
        if not 0 <= self.volume <= 1:
            raise ValueError("music_volume must be between 0 and 1")
        self.current_song = None
        self.is_playing = False
        self.is_paused = False
        self.was_paused_for_conversation = False
        self._alert_ducked = False
        self._generation = 0
        self._art_task = None
        self._closed = False
        self.cache_dir = str(PROJECT_ROOT / "music_cache")
        self.metadata_file = os.path.join(self.cache_dir, "metadata.json")
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        self.album_art = AlbumArt(Path(self.cache_dir), self._log)
        self.ytmusic = YTMusic()
        # Delay opening the output device until a track is actually requested.
        self._log("MUSIC_INIT", "YouTube Music player ready")

    def _log(self, kind: str, message: str) -> None:
        if self.log_function:
            self.log_function(kind, message)
        else:
            logger.info("[%s] %s", kind, log_message(kind, message))

    def _refresh_playback(self) -> None:
        # pygame reports not busy while paused, which is not the end of a song.
        if self.is_playing and not self.is_paused:
            if not pygame.mixer.get_init() or not pygame.mixer.music.get_busy():
                self._clear_track()

    def _clear_track(self) -> None:
        self.is_playing = False
        self.is_paused = False
        self.was_paused_for_conversation = False
        self.current_song = None

    def _generate_song_id(self, video_id: str, title: str, artist: str) -> str:
        # Preserve existing cache filenames; this is an identifier, not a checksum.
        value = f"{video_id}_{title}_{artist}".lower()
        return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()[:12]

    def _get_cached_file_path(self, song_id: str) -> str:
        return os.path.join(self.cache_dir, f"{song_id}.mp3")

    def _load_metadata(self) -> dict:
        try:
            data = json.loads(Path(self.metadata_file).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Cache metadata must be an object")
            return {
                key: entry
                for key, entry in data.items()
                if re.fullmatch(r"[0-9a-f]{12}", key) and isinstance(entry, dict)
            }
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            self._log("CACHE_ERROR", f"Cannot read cache metadata: {error}")
            return {}

    def _save_metadata(self, metadata: dict) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.cache_dir, suffix=".json", delete=False
            ) as output:
                temporary = Path(output.name)
                json.dump(metadata, output, indent=2, ensure_ascii=False)
                output.write("\n")
            temporary.replace(self.metadata_file)
        except OSError as error:
            self._log("CACHE_ERROR", f"Cannot save cache metadata: {error}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _cache_song(self, song_id, video_id, title, artist, thumbnail_url=None) -> None:
        metadata = self._load_metadata()
        entry = metadata.get(song_id, {})
        now = datetime.now().isoformat(timespec="seconds")
        count = entry.get("play_count", 0)
        entry.update(
            video_id=video_id,
            title=title,
            artist=artist,
            last_played=now,
            play_count=(count if isinstance(count, int) else 0) + 1,
        )
        entry.setdefault("cached_at", now)
        entry.setdefault("cached_timestamp", time.time())
        if thumbnail_url:
            entry["thumbnail_url"] = thumbnail_url
        metadata[song_id] = entry
        self._save_metadata(metadata)

    async def search_songs(self, query: str, limit: int = 5) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or limit < 1:
            return []
        try:
            self._log("MUSIC_SEARCH", f"Searching for: {query}")
            results = await asyncio.to_thread(
                self.ytmusic.search, query, filter="songs", limit=limit
            )
            songs = []
            for result in results:
                video_id = result.get("videoId")
                if not isinstance(video_id, str) or not re.fullmatch(
                    r"[\w-]{11}", video_id, re.ASCII
                ):
                    continue
                artists = result.get("artists") or []
                songs.append(
                    {
                        "videoId": video_id,
                        "title": result.get("title") or "Unknown Title",
                        "artist": ", ".join(a["name"] for a in artists if a.get("name"))
                        or "Unknown Artist",
                        "duration": result.get("duration") or "Unknown",
                        "thumbnail": self._get_hires_thumbnail_url(result.get("thumbnails") or []),
                    }
                )
            return songs
        except Exception as error:
            self._log("MUSIC_ERROR", f"Search failed: {error}")
            return []

    @staticmethod
    def _get_hires_thumbnail_url(thumbnails: list, size: int = 2000) -> str | None:
        if not thumbnails:
            return None
        url = thumbnails[-1].get("url")
        return re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", url) if url else None

    async def _download_song(self, video_id: str, output_path: str) -> bool:
        """Publish a completed MP3 atomically, including when downloads overlap."""

        cancelled = threading.Event()

        def check_cancelled(progress=None):
            if cancelled.is_set():
                raise yt_dlp.utils.DownloadError("Download cancelled")
            if isinstance(progress, dict) and progress.get("downloaded_bytes", 0) > MAX_SONG_BYTES:
                raise yt_dlp.utils.DownloadError("Song exceeds the 200 MiB download limit")

        def filter_track(info, *, incomplete=False):
            if info.get("is_live"):
                return "Live streams are not supported"
            duration = info.get("duration")
            if duration is not None and duration > MAX_SONG_SECONDS:
                return "Songs longer than two hours are not supported"

        def download():
            # The worker owns its staging directory even if its awaiting task is cancelled.
            with tempfile.TemporaryDirectory(prefix=".download-", dir=self.cache_dir) as staging:
                options = {
                    "format": "bestaudio/best",
                    "outtmpl": f"{staging}/audio.%(ext)s",
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "max_filesize": MAX_SONG_BYTES,
                    "match_filter": filter_track,
                    "socket_timeout": 15,
                    "retries": 2,
                    "progress_hooks": [check_cancelled],
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                }
                with yt_dlp.YoutubeDL(options) as downloader:
                    downloader.download([f"https://music.youtube.com/watch?v={video_id}"])
                result = Path(staging) / "audio.mp3"
                if not result.is_file() or result.stat().st_size == 0:
                    raise OSError("Download produced no audio")
                if result.stat().st_size > MAX_SONG_BYTES:
                    raise OSError("Converted song exceeds the 200 MiB size limit")
                check_cancelled()
                result.replace(output_path)

        try:
            await asyncio.to_thread(download)
            return True
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except Exception as error:
            self._log("CACHE_ERROR", f"Download failed: {error}")
            return False

    async def play_song(
        self,
        video_id: str,
        title: str = "Unknown",
        artist: str = "Unknown",
        thumbnail_url: str | None = None,
    ) -> bool:
        if (
            self._closed
            or not isinstance(video_id, str)
            or not re.fullmatch(r"[\w-]{11}", video_id, re.ASCII)
        ):
            return False
        # stop can yield while joining old artwork. A newer request must win if
        # it starts during that handoff, just as it does during audio downloads.
        generation = self._generation + 1
        await self.stop()
        if generation != self._generation or self._closed:
            return False
        song_id = self._generate_song_id(video_id, title, artist)
        audio_file = Path(self._get_cached_file_path(song_id))
        try:
            if not audio_file.is_file() or audio_file.stat().st_size == 0:
                if not await self._download_song(video_id, str(audio_file)):
                    return False
            if generation != self._generation or self._closed:
                return False
            if not thumbnail_url:
                thumbnail_url = self._load_metadata().get(song_id, {}).get("thumbnail_url")
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.mixer.music.load(str(audio_file))
            # Loading a track resets pygame's volume.
            pygame.mixer.music.set_volume(self.volume * (0.2 if self._alert_ducked else 1))
            pygame.mixer.music.play()
            self.current_song = {
                "videoId": video_id,
                "title": title,
                "artist": artist,
                "song_id": song_id,
                "audio_file": str(audio_file),
            }
            self.is_playing = True
            self.is_paused = False
            self._cache_song(song_id, video_id, title, artist, thumbnail_url)
            self._log("MUSIC_PLAYBACK", f"Playing: {title} by {artist}")
            # Optional artwork must not delay playback or returning to wake detection.
            if thumbnail_url and self.album_art.is_visible():
                self._art_task = asyncio.create_task(
                    self._show_album_art(thumbnail_url, song_id, title, artist, generation)
                )
            return True
        except asyncio.CancelledError:
            if generation == self._generation:
                await self.stop()
            raise
        except Exception as error:
            if generation == self._generation:
                await self.stop()
            self._log("MUSIC_ERROR", f"Playback failed: {error}")
            return False

    async def _show_album_art(
        self, url: str, song_id: str, title: str, artist: str, generation: int
    ) -> None:
        try:
            thumbnail = await self.album_art.download(url, song_id)
            if thumbnail and generation == self._generation and not self._closed:
                self._refresh_playback()
                if self.is_playing:
                    self.album_art.render(thumbnail, title, artist)
        except Exception as error:
            self._log("ART_ERROR", f"Cannot show album art: {error}")

    def _cancel_album_art(self) -> asyncio.Task | None:
        task, self._art_task = self._art_task, None
        if task is not None:
            task.cancel()
        return task

    async def pause(self) -> bool:
        self._refresh_playback()
        if not self.is_playing:
            return False
        pygame.mixer.music.pause()
        self.is_paused = True
        self.was_paused_for_conversation = False
        return True

    def set_alert_ducked(self, ducked: bool) -> None:
        """Timer sounds change gain only, never playback or auto-resume intent."""
        if self._alert_ducked == ducked:
            return
        self._alert_ducked = ducked
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(self.volume * (0.2 if ducked else 1))

    async def resume(self) -> bool:
        self._refresh_playback()
        if not (self.is_playing and self.is_paused):
            return False
        pygame.mixer.music.unpause()
        self.is_paused = False
        self.was_paused_for_conversation = False
        return True

    async def pause_for_conversation(self) -> bool:
        self._refresh_playback()
        if not self.is_playing or self.is_paused:
            return False
        await self.pause()
        self.was_paused_for_conversation = True
        return True

    async def resume_after_conversation(self) -> bool:
        if not self.was_paused_for_conversation:
            return False
        return await self.resume()

    async def stop(self) -> bool:
        """Also invalidate pending searches/downloads before they can start a track."""
        self._generation += 1
        art = self._cancel_album_art()
        had_track = self.is_playing
        self._clear_track()
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        finally:
            if art is not None:
                await asyncio.gather(art, return_exceptions=True)
        return had_track

    def get_status(self) -> dict:
        self._refresh_playback()
        return {
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "current_song": dict(self.current_song) if self.current_song else None,
        }

    def get_cache_info(self) -> dict:
        entries = {
            key: value
            for key, value in self._load_metadata().items()
            if Path(self._get_cached_file_path(key)).is_file()
        }
        size = sum(Path(self._get_cached_file_path(key)).stat().st_size for key in entries)
        return {
            "total_songs": len(entries),
            "total_size_mb": round(size / 1024**2, 2),
            "cache_dir": self.cache_dir,
            "most_played": sorted(
                entries.items(),
                key=lambda item: (
                    item[1].get("play_count", 0)
                    if isinstance(item[1].get("play_count", 0), int)
                    else 0
                ),
                reverse=True,
            )[:5],
        }

    async def play_search_result(self, query: str, index: int = 0) -> bool:
        if index < 0 or self._closed:
            return False
        self._generation += 1
        generation = self._generation
        songs = await self.search_songs(query, limit=max(5, index + 1))
        if generation != self._generation or self._closed or index >= len(songs):
            return False
        song = songs[index]
        return await self.play_song(
            song["videoId"], song["title"], song["artist"], song["thumbnail"]
        )

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._cancel_album_art()
        self._clear_track()
        if pygame.mixer.get_init():
            pygame.mixer.quit()
