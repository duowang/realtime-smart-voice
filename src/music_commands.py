"""Validate Realtime tool calls and translate player state into spoken results."""

import logging

from youtube_music_player import YouTubeMusicPlayer


class MusicCommandHandler:
    def __init__(self, log_function=None, music_volume: float | None = None):
        self.log_function = log_function
        self.music_player = YouTubeMusicPlayer(log_function, volume=music_volume)

    def _log(self, kind: str, message: str) -> None:
        if self.log_function:
            self.log_function(kind, message)
        else:
            logging.getLogger(__name__).info("[%s] %s", kind, message)

    @staticmethod
    def _result(success: bool, action: str, response: str, **details) -> dict:
        return {"success": success, "action": action, "response": response, **details}

    async def execute(self, function_name: str, arguments: dict) -> dict:
        handlers = {
            "play_music": self._play,
            "pause_music": self._pause,
            "resume_music": self._resume,
            "stop_music": self._stop,
            "get_music_status": self._status,
            "skip_song": self._skip,
        }
        handler = handlers.get(function_name)
        if handler is None:
            return self._result(False, "unknown", f"Unknown music function: {function_name}")
        if not isinstance(arguments, dict):
            return self._result(False, "invalid_arguments", "Music arguments must be an object.")
        if function_name == "play_music":
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                return self._result(False, "invalid_arguments", "Please provide a song or artist.")
            arguments = {"query": query.strip()}
        self._log("MUSIC_FUNCTION_CALL", f"{function_name}({arguments})")
        try:
            return await handler(arguments)
        except Exception as error:
            self._log("MUSIC_ERROR", f"{function_name} failed: {error}")
            return self._result(False, "error", "The music command failed. Please try again.")

    async def _play(self, arguments: dict) -> dict:
        query = arguments["query"]
        if not await self.music_player.play_search_result(query):
            return self._result(
                False, "play_failed", f"I couldn't find or play '{query}'.", query=query
            )
        status = self.get_status()
        song = status["current_song"] or {}
        return self._result(True, "play", f"Now playing {song.get('title', query)}.", query=query)

    async def _pause(self, _) -> dict:
        # Always reach pause even when wake-up already auto-paused this track:
        # an explicit pause must clear the automatic-resume flag.
        if await self.music_player.pause():
            return self._result(True, "pause", "Music paused.")
        return self._result(False, "pause_no_music", "There's no music playing to pause.")

    async def _resume(self, _) -> dict:
        if await self.music_player.resume():
            return self._result(True, "resume", "Music resumed.")
        if self.get_status()["is_playing"]:
            return self._result(True, "resume", "The music is already playing.")
        return self._result(False, "resume_no_music", "There's no music to resume.")

    async def _stop(self, _) -> dict:
        stopped = await self.music_player.stop()
        return self._result(True, "stop", "Music stopped." if stopped else "No music is playing.")

    async def _skip(self, _) -> dict:
        await self.music_player.stop()
        return self._result(True, "next", "Skipped. Ask me to play another song.")

    async def _status(self, _) -> dict:
        status = self.get_status()
        if not status["is_playing"]:
            return self._result(True, "status", "No music is playing.", status="not_playing")
        state = "paused" if status["is_paused"] else "playing"
        title = (status["current_song"] or {}).get("title", "Unknown song")
        return self._result(
            True, "status", f"Currently {state}: {title}.", status=state, song=title
        )

    async def pause_for_conversation(self) -> bool:
        return await self.music_player.pause_for_conversation()

    async def resume_after_conversation(self) -> bool:
        return await self.music_player.resume_after_conversation()

    def get_status(self) -> dict:
        return self.music_player.get_status()

    def cleanup(self) -> None:
        self.music_player.cleanup()

    async def aclose(self) -> None:
        """Join optional artwork before releasing playback and its logging owner."""
        try:
            await self.music_player.stop()
        finally:
            self.cleanup()
