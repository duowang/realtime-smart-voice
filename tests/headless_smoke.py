"""Live integration check using WAV input and SDL's silent music output.

Run directly in a separate process: this check needs the real model, network
and mixer, unlike the offline pytest suite.
Requires the normal OpenAI key and network access to OpenAI/YouTube Music.
"""

import argparse
import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
# Must be set before importing pygame or initializing any audio components.
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402

from realtime_voice_assistant import RealtimeVoiceAssistant  # noqa: E402


def read_pcm(path: Path, rate: int) -> bytes:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, rate):
            raise ValueError(f"{path} must be mono PCM16 at {rate} Hz")
        pcm = source.readframes(source.getnframes())
        if not pcm:
            raise ValueError(f"{path} is empty")
        return pcm


class FileStream:
    """Replace only the physical PortAudio device, keeping production consumers."""

    def __init__(self, pcm: bytes, rate: int, realtime: bool):
        self.pcm = pcm
        self.rate = rate
        self.realtime = realtime
        self.cursor = 0
        self.closed = False
        self.written_bytes = 0

    def read(self, frames, **_):
        if self.closed:
            raise OSError("read after stream close")
        if self.realtime:
            time.sleep(frames / self.rate)
        chunk = self.pcm[self.cursor : self.cursor + frames * 2]
        self.cursor += frames * 2
        return chunk.ljust(frames * 2, b"\0")

    def write(self, pcm):
        if self.closed:
            raise OSError("write after stream close")
        self.written_bytes += len(pcm)

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class FileAudio:
    def __init__(self, inputs, streams):
        self.inputs = inputs
        self.streams = streams
        self.owned = []

    def open(self, *, rate, input=False, **_):
        stream = FileStream(
            self.inputs.get(rate, b"") if input else b"", rate, input and rate == 24000
        )
        self.owned.append(stream)
        self.streams.append(stream)
        return stream

    def terminate(self):
        for stream in self.owned:
            stream.close()


async def run(args):
    wake_pcm = read_pcm(args.wake_audio, 16000)
    commands = {
        name: read_pcm(args.commands_dir / f"{name}.wav", 24000)
        for name in ("play", "pause", "resume", "stop")
    }
    background = read_pcm(args.background_audio, 16000) if args.background_audio else None
    inputs, streams, events = {}, [], []
    report = {
        "checks": [],
        "audio_driver": "SDL dummy",
        "live_services": True,
        "background_snr_db": args.snr_db if background else None,
    }

    class HeadlessAssistant(RealtimeVoiceAssistant):
        def _setup_logging(self):
            pass

        def _log_event(self, kind, message):
            events.append((kind, message))

    def record(name, **details):
        report["checks"].append({"name": name, "passed": True, **details})
        print(f"PASS: {name}", flush=True)

    async def wake(assistant):
        pcm = wake_pcm
        status = assistant.music_handler.get_status()
        if background and status["is_playing"] and not status["is_paused"]:
            # Controlled digital mixture; physical room acoustics aren't simulated.
            speech = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
            voice_rms = np.sqrt(np.mean(speech**2))
            # Continuous music is present before and after the spoken phrase.
            speech = np.pad(speech, (16000, 16000))
            music = np.resize(np.frombuffer(background, dtype=np.int16), speech.size).astype(
                np.float32
            )
            music_rms = np.sqrt(np.mean(music**2))
            if voice_rms > 0 and music_rms > 0:
                music *= voice_rms / music_rms / 10 ** (args.snr_db / 20)
            pcm = np.clip(speech + music, -32768, 32767).astype(np.int16).tobytes()
        inputs[16000] = pcm + b"\0" * 32000
        for _ in range(len(inputs[16000]) // 1024 + 2):
            detected = await assistant.wake_word_detector.listen_for_wake_word()
            if detected:
                if assistant.wake_word_detector.is_listening:
                    raise AssertionError("Wake detector failed to release its input stream")
                return detected
        await assistant.wake_word_detector.stop_listening()
        raise AssertionError("Wake phrase was not detected")

    assistant = None
    try:
        with patch("pyaudio.PyAudio", side_effect=lambda: FileAudio(inputs, streams)):
            assistant = HeadlessAssistant(str(args.config))
            player = assistant.music_handler.music_player
            # Album art isn't part of the audio/control test.
            player.album_art.download = AsyncMock(return_value=None)
            player.album_art.render = lambda *_: None
            for name in ("play", "pause", "resume", "stop"):
                detected = await wake(assistant)
                record(f"wake before {name}", phrase=detected)
                inputs[24000] = b"\0" * 14400 + commands[name]
                event_start = len(events)
                await asyncio.wait_for(assistant.handle_wake_word_detection(), timeout=args.timeout)
                turn_events = events[event_start:]
                expected_function = f"{name}_music"
                calls = [message for kind, message in turn_events if kind == "FUNCTION_CALL"]
                if not any(message.startswith(expected_function + "(") for message in calls):
                    transcripts = [m for k, m in turn_events if k == "USER_TRANSCRIPT"]
                    raise AssertionError(
                        f"Expected {expected_function}; got calls={calls}, transcripts={transcripts}"
                    )

                status = player.get_status()
                await asyncio.sleep(0.2)
                busy = pygame.mixer.music.get_busy()
                position = pygame.mixer.music.get_pos()
                await asyncio.sleep(0.25)
                next_position = pygame.mixer.music.get_pos()
                if name in ("play", "resume"):
                    assert status["is_playing"] and not status["is_paused"] and busy
                    assert next_position > position, "Playback clock didn't advance"
                elif name == "pause":
                    assert status["is_playing"] and status["is_paused"] and not busy
                    assert next_position == position, "Paused playback clock advanced"
                    assert not player.was_paused_for_conversation, (
                        "Explicit pause would auto-resume"
                    )
                else:
                    assert not status["is_playing"] and not status["is_paused"] and not busy
                    assert status["current_song"] is None
                    assert not await assistant.music_handler.resume_after_conversation()
                record(
                    name,
                    function=expected_function,
                    mixer_busy=busy,
                    position_ms=position,
                    next_position_ms=next_position,
                )

            await wake(assistant)
            assert not pygame.mixer.music.get_busy()
            record("wake after stop without restarting music")
            report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = str(error)
        print(f"FAIL: {error}", flush=True)
    finally:
        if assistant is not None:
            await assistant.cleanup()
        report["all_streams_closed"] = all(stream.closed for stream in streams)
        report["mixer_closed"] = not bool(pygame.mixer.get_init())
        report["output_bytes"] = sum(stream.written_bytes for stream in streams)
        if not report["all_streams_closed"] or not report["mixer_closed"]:
            report["passed"] = False
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wake-audio", type=Path, required=True, help="Mono PCM16 wake phrase at 16 kHz"
    )
    parser.add_argument(
        "--commands-dir",
        type=Path,
        required=True,
        help="Mono PCM16 24 kHz play.wav, pause.wav, resume.wav and stop.wav",
    )
    parser.add_argument("--background-audio", type=Path, help="Optional mono PCM16 music at 16 kHz")
    parser.add_argument(
        "--snr-db",
        type=float,
        default=5,
        help="Speech/music ratio in the digital wake-word mixture (default: 5 dB)",
    )
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "config.json")
    parser.add_argument(
        "--timeout", type=float, default=45, help="Maximum seconds per conversation"
    )
    parser.add_argument("--report", type=Path, help="Optional JSON result file; keep it out of Git")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
