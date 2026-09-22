#!/usr/bin/env python3
"""Coordinate wake detection, conversation handoff and application shutdown."""

import argparse
import asyncio
import logging
import signal
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np
import pyaudio
import soundfile as sf

from audio_io import audio_operation, close_stream
from configuration import DEFAULT_CONFIG_FILE, PROJECT_ROOT, get_api_key, load_config
from music_commands import MusicCommandHandler
from realtime_voice_client import RealtimeVoiceClient
from wake_word_detector import WakeWordDetector


class RealtimeVoiceAssistant:
    def __init__(self, config_file: str | Path = DEFAULT_CONFIG_FILE):
        self.config = load_config(config_file)
        get_api_key(self.config)  # Validate before downloading models or opening devices.
        self.running = False
        self._shutting_down = False
        self._cleaned_up = False
        self.music_handler = None
        self.wake_word_detector = None
        self.realtime_client = None
        self._setup_logging()
        try:
            self.music_handler = MusicCommandHandler(
                self._log_event, self.config.get("music_volume")
            )
            self.realtime_client = RealtimeVoiceClient(
                self.config, self._log_event, self.music_handler
            )
            self.wake_word_detector = WakeWordDetector(self.config, self._log_event)
        except BaseException:
            # Constructors acquire no realtime audio/socket resources. Release the
            # components already built if a later constructor fails.
            if self.wake_word_detector is not None:
                self.wake_word_detector.cleanup()
            if self.music_handler is not None:
                self.music_handler.cleanup()
            self._close_logging()
            raise

    def _setup_logging(self) -> None:
        directory = PROJECT_ROOT / "logs"
        directory.mkdir(exist_ok=True)
        # An instance owns its handler; constructing another assistant must not
        # clear or close the first one's handlers.
        self.logger = logging.getLogger(f"realtime_voice_assistant.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self._log_handler = RotatingFileHandler(
            directory / "realtime_voice_assistant.log",
            maxBytes=5_000_000,
            backupCount=2,
            encoding="utf-8",
        )
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        self.logger.addHandler(self._log_handler)

    def _close_logging(self) -> None:
        handler = getattr(self, "_log_handler", None)
        if handler is not None:
            self.logger.removeHandler(handler)
            handler.close()
            self._log_handler = None

    def _log_event(self, kind: str, message: str) -> None:
        self.logger.info("%s: %s", kind, message)

    async def _play_audio_file(self, path: str | Path, description: str, log_prefix: str) -> None:
        audio = stream = None
        try:
            data, rate = sf.read(path, dtype="float32", always_2d=True)
            if not data.size:
                raise ValueError("Audio prompt is empty")
            peak = float(np.max(np.abs(data)))
            if peak > 1:
                data /= peak
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paFloat32,
                channels=data.shape[1],
                rate=int(rate),
                output=True,
                frames_per_buffer=1024,
            )
            for offset in range(0, len(data), 1024):
                await audio_operation(stream.write, data[offset : offset + 1024].tobytes())
            await asyncio.sleep(0.3)
        except Exception as error:
            self._log_event(f"{log_prefix}_ERROR", f"Cannot play {description}: {error}")
        finally:
            close_stream(stream)
            if audio is not None:
                audio.terminate()

    async def play_wake_word_acknowledgment(self) -> None:
        await self._play_audio_file(
            PROJECT_ROOT / "audio" / "hi_there.wav", "greeting", "WAKE_WORD_ACK"
        )

    async def play_bye_bye_sound(self) -> None:
        if not self.music_handler.get_status()["is_playing"]:
            await self._play_audio_file(
                PROJECT_ROOT / "audio" / "bye_bye.wav", "goodbye", "BYE_BYE"
            )

    async def handle_wake_word_detection(self) -> None:
        try:
            # Cover greeting, connection setup, tool work, and the conversation.
            async with asyncio.timeout(self.config.get("conversation_timeout", 120)):
                await self.music_handler.pause_for_conversation()
                await self.play_wake_word_acknowledgment()
                self._log_event("CONVERSATION_START", "Starting conversation after wake word")
                await self.realtime_client.start_conversation()
        except TimeoutError:
            self._log_event("CONVERSATION_TIMEOUT", "Returning to wake-word detection")
        except Exception as error:
            self._log_event("CONVERSATION_ERROR", str(error))
            print(f"Conversation failed: {error}")
        finally:
            # Also restores an automatic pause when greeting/connection setup fails.
            await self.realtime_client.stop_conversation(resume_music=not self._shutting_down)

    async def run_continuous_mode(self) -> None:
        print(
            f"Listening for {', '.join(self.wake_word_detector.wake_keywords)}. Press Ctrl+C to exit."
        )
        self.running = True
        loop = asyncio.get_running_loop()
        owner = asyncio.current_task()
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

        def request_shutdown():
            if not self._shutting_down:
                self._shutting_down = True
                self.running = False
                self.realtime_client.request_stop(resume_music=False)
                owner.cancel()

        for sig in previous:
            loop.add_signal_handler(sig, request_shutdown)
        try:
            while self.running:
                keyword = await self.wake_word_detector.listen_for_wake_word()
                if keyword:
                    await self.handle_wake_word_detection()
                    await self.play_bye_bye_sound()
                    print("Ready for next wake word.")
        except asyncio.CancelledError:
            if not self._shutting_down:
                raise
        finally:
            self.running = False
            self._shutting_down = True
            for sig, handler in previous.items():
                loop.remove_signal_handler(sig)
                signal.signal(sig, handler)
            await self.cleanup()

    async def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        self._shutting_down = True
        try:
            if self.realtime_client is not None:
                await self.realtime_client.cleanup()
        finally:
            try:
                if self.wake_word_detector is not None:
                    self.wake_word_detector.cleanup()
            finally:
                try:
                    if self.music_handler is not None:
                        self.music_handler.cleanup()
                finally:
                    self._close_logging()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_FILE, help="Configuration file"
    )
    args = parser.parse_args()
    try:
        assistant = RealtimeVoiceAssistant(args.config)
        await assistant.run_continuous_mode()
    except Exception as error:
        print(f"Assistant failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
