"""Offline wake-word detection using sherpa-onnx and the local microphone."""

import logging
import math
import tempfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pyaudio
import sentencepiece as spm
import sherpa_onnx

from audio_io import audio_operation, close_stream
from configuration import normalize_wake_phrase
from wake_word_model import DEFAULT_MODEL_DIR, PROJECT_ROOT, ensure_wake_word_model

SAMPLE_RATE = 16000
FRAME_LENGTH = 512
DEFAULT_THRESHOLD = 0.1
DEFAULT_INPUT_BOOST = 4.0
MAX_ACTIVE_PATHS = 8


def encode_keywords(keywords: list[str], tokenizer_path: Path) -> tuple[str, dict[str, str]]:
    """Encode English phrases with the exact subword vocabulary used by the model."""
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("wake_keywords must be a non-empty list of English phrases")
    tokenizer = spm.SentencePieceProcessor(model_file=str(tokenizer_path))

    encoded = []
    labels = {}
    for index, phrase in enumerate(keywords):
        phrase = normalize_wake_phrase(phrase)
        pieces = tokenizer.encode(phrase.upper(), out_type=str)
        if not pieces or "<unk>" in pieces:
            raise ValueError(
                f"Cannot tokenize wake phrase '{phrase}'; choose another English phrase"
            )
        label = f"wake_{index}"
        labels[label] = phrase
        encoded.append(f"{' '.join(pieces)} @{label}")
    return "\n".join(encoded), labels


class WakeWordDetector:
    """Keep the wake-word stream separate from the assistant's conversation audio."""

    def __init__(self, config: dict, log_function: Callable | None = None):
        self.config = config
        self.log_function = log_function
        self.audio = None
        self.stream = None
        self.keyword_stream = None
        self.boosted_keyword_stream = None
        self.is_listening = False
        self.wake_keywords = config.get("wake_keywords", ["Hi Taco"])

        threshold = float(config.get("wake_word_threshold", DEFAULT_THRESHOLD))
        if not 0 < threshold <= 1:
            raise ValueError("wake_word_threshold must be greater than 0 and at most 1")
        boost = config.get("wake_word_input_boost", DEFAULT_INPUT_BOOST)
        if type(boost) not in (int, float) or not math.isfinite(boost) or not 1 <= boost <= 8:
            raise ValueError("wake_word_input_boost must be between 1 and 8")
        self.input_boost = float(boost)
        model_dir = Path(config.get("wake_word_model_dir", DEFAULT_MODEL_DIR)).expanduser()
        if not model_dir.is_absolute():
            model_dir = PROJECT_ROOT / model_dir
        paths = ensure_wake_word_model(model_dir)
        self._keywords, self._keyword_labels = encode_keywords(
            self.wake_keywords, paths["tokenizer"]
        )
        # sherpa reads this file during construction. A private temporary file
        # lets concurrent assistants use different phrases without overwriting one another.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8") as keywords:
            keywords.write(self._keywords + "\n")
            keywords.flush()
            self.spotter = sherpa_onnx.KeywordSpotter(
                tokens=str(paths["tokens"]),
                encoder=str(paths["encoder"]),
                decoder=str(paths["decoder"]),
                joiner=str(paths["joiner"]),
                keywords_file=keywords.name,
                sample_rate=SAMPLE_RATE,
                num_threads=1,
                keywords_score=1.0,
                keywords_threshold=threshold,
                # Keep alternate token paths alive for accented/connected speech.
                max_active_paths=MAX_ACTIVE_PATHS,
                num_trailing_blanks=1,
                provider="cpu",
            )
        self.audio = pyaudio.PyAudio()
        self._log(
            "WAKE_WORD_INIT",
            f"sherpa-onnx ready for {', '.join(self.wake_keywords)} "
            f"(quiet-input boost {self.input_boost:g}x)",
        )

    def _log(self, log_type: str, message: str):
        if self.log_function:
            self.log_function(log_type, message)
        else:
            logging.getLogger(__name__).info("[%s] %s", log_type, message)

    async def start_listening(self):
        if self.is_listening:
            return
        # A fresh decoder stream prevents pre-conversation audio from triggering
        # again when control returns from the Realtime client.
        self.keyword_stream = self.spotter.create_stream()
        if self.input_boost > 1:
            self.boosted_keyword_stream = self.spotter.create_stream()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=FRAME_LENGTH,
        )
        self.is_listening = True
        print(f"Started listening for wake word: {', '.join(self.wake_keywords)}")
        self._log("WAKE_WORD_START", "Started offline wake-word detection")

    def process_audio(self, audio_frame: bytes) -> str | None:
        """Try original and boosted PCM on separate decoder histories.

        The original path preserves louder speech that can distort when boosted.
        Both histories are reset together after a hit so one phrase cannot wake twice.
        """
        if self.keyword_stream is None:
            self.keyword_stream = self.spotter.create_stream()
        if self.input_boost > 1 and self.boosted_keyword_stream is None:
            self.boosted_keyword_stream = self.spotter.create_stream()
        samples = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32) / 32768.0
        streams = [(self.keyword_stream, samples)]
        if self.boosted_keyword_stream is not None:
            boosted = np.clip(samples * self.input_boost, -1.0, 1.0)
            streams.append((self.boosted_keyword_stream, boosted))
        for stream, waveform in streams:
            stream.accept_waveform(SAMPLE_RATE, waveform)
            while self.spotter.is_ready(stream):
                self.spotter.decode_stream(stream)
                result = self.spotter.get_result(stream)
                if result:
                    for decoder, _ in streams:
                        self.spotter.reset_stream(decoder)
                    return self._keyword_labels[result]
        return None

    async def listen_for_wake_word(self) -> str | None:
        if not self.is_listening:
            await self.start_listening()
        audio_frame = await audio_operation(
            self.stream.read, FRAME_LENGTH, exception_on_overflow=False
        )
        keyword = self.process_audio(audio_frame)
        if keyword:
            self._log("WAKE_WORD_DETECTED", f"sherpa-onnx detected: '{keyword}'")
            await self.stop_listening()
        return keyword

    def _close_stream(self):
        self.is_listening = False
        self.keyword_stream = None
        self.boosted_keyword_stream = None
        stream, self.stream = self.stream, None
        if stream is not None:
            close_stream(stream)

    async def stop_listening(self):
        self._close_stream()

    def get_sample_rate(self) -> int:
        return SAMPLE_RATE

    def cleanup(self):
        try:
            self._close_stream()
        finally:
            if self.audio is not None:
                audio, self.audio = self.audio, None
                audio.terminate()
            self.spotter = None
        self._log("WAKE_WORD_STOP", "Wake-word detector cleaned up")
