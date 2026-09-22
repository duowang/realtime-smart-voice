"""Offline wake-word detection using sherpa-onnx and the local microphone."""

import logging
import re
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pyaudio
import sherpa_onnx

from wake_word_model import DEFAULT_MODEL_DIR, PROJECT_ROOT, ensure_wake_word_model

SAMPLE_RATE = 16000
FRAME_LENGTH = 512
DEFAULT_THRESHOLD = 0.25


def encode_keywords(keywords: list[str], lexicon_path: Path) -> tuple[str, dict[str, str]]:
    """Map English phrases to model phonemes and safe, unambiguous result labels."""
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("wake_keywords must be a non-empty list of English phrases")
    lexicon = {}
    with lexicon_path.open(encoding="utf-8") as source:
        for line in source:
            parts = line.split()
            if len(parts) > 1:
                lexicon.setdefault(parts[0].upper(), parts[1:])

    encoded = []
    labels = {}
    for index, phrase in enumerate(keywords):
        if not isinstance(phrase, str) or not re.fullmatch(
            r"[A-Za-z]+(?:'[A-Za-z]+)*(?:\s+[A-Za-z]+(?:'[A-Za-z]+)*)*", phrase.strip()
        ):
            raise ValueError("wake_keywords must contain English words separated by spaces")
        phrase = " ".join(phrase.split())
        phones = []
        for word in phrase.upper().split():
            if word not in lexicon:
                raise ValueError(
                    f"Wake word '{word}' is not in the model's English pronunciation dictionary. "
                    "Choose another phrase in config/config.json: wake_keywords."
                )
            phones.extend(lexicon[word])
        label = f"wake_{index}"
        labels[label] = phrase
        encoded.append(f"{' '.join(phones)} @{label}")
    return "\n".join(encoded), labels


class WakeWordDetector:
    """Keep the wake-word stream separate from the assistant's conversation audio."""

    def __init__(self, config: dict, log_function: Optional[Callable] = None):
        self.config = config
        self.log_function = log_function
        self.audio = None
        self.stream = None
        self.keyword_stream = None
        self.is_listening = False
        self.wake_keywords = config.get("wake_keywords", ["Hi Taco"])

        threshold = float(config.get("wake_word_threshold", DEFAULT_THRESHOLD))
        if not 0 < threshold <= 1:
            raise ValueError("wake_word_threshold must be greater than 0 and at most 1")
        model_dir = Path(config.get("wake_word_model_dir", DEFAULT_MODEL_DIR)).expanduser()
        if not model_dir.is_absolute():
            model_dir = PROJECT_ROOT / model_dir
        paths = ensure_wake_word_model(model_dir)
        self._keywords, self._keyword_labels = encode_keywords(self.wake_keywords, paths["lexicon"])
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
                num_trailing_blanks=2,
                provider="cpu",
            )
        self.audio = pyaudio.PyAudio()
        self._log("WAKE_WORD_INIT", f"sherpa-onnx ready for {', '.join(self.wake_keywords)}")

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

    def process_audio(self, audio_frame: bytes) -> Optional[str]:
        """Feed PCM16 microphone audio to sherpa as normalized float32 samples."""
        if self.keyword_stream is None:
            self.keyword_stream = self.spotter.create_stream()
        samples = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32) / 32768.0
        self.keyword_stream.accept_waveform(SAMPLE_RATE, samples)
        while self.spotter.is_ready(self.keyword_stream):
            self.spotter.decode_stream(self.keyword_stream)
            result = self.spotter.get_result(self.keyword_stream)
            if result:
                self.spotter.reset_stream(self.keyword_stream)
                return self._keyword_labels[result]
        return None

    async def listen_for_wake_word(self) -> Optional[str]:
        if not self.is_listening:
            await self.start_listening()
        audio_frame = self.stream.read(FRAME_LENGTH, exception_on_overflow=False)
        keyword = self.process_audio(audio_frame)
        if keyword:
            self._log("WAKE_WORD_DETECTED", f"sherpa-onnx detected: '{keyword}'")
            await self.stop_listening()
        return keyword

    def _close_stream(self):
        self.is_listening = False
        self.keyword_stream = None
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.stop_stream()
            finally:
                stream.close()

    async def stop_listening(self):
        self._close_stream()

    def get_sample_rate(self) -> int:
        return SAMPLE_RATE

    def cleanup(self):
        try:
            self._close_stream()
        finally:
            if self.audio is not None:
                self.audio.terminate()
                self.audio = None
            self.spotter = None
        self._log("WAKE_WORD_STOP", "Wake-word detector cleaned up")
