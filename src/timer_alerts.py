"""Bounded local timer chimes on a mixer channel separate from music."""

import logging

import numpy as np
import pygame


class TimerAlerts:
    def __init__(self, duck_music, *, volume: float = 0.25, duration: float = 10):
        self.duck_music = duck_music
        self.volume, self.duration = volume, duration
        self._channel = None
        self._sound = None
        self._timer_ids = set()

    def ring(self, timers: list[dict]) -> None:
        """SDL bounds playback even if the Python scheduler is temporarily busy."""
        self.hush()
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        rate, sample_format, channels = pygame.mixer.get_init()
        if sample_format != -16:
            raise RuntimeError("Timer chimes require a PCM16 mixer")
        # Two softly faded pips with a long gap leave room to hear the wake phrase.
        samples = np.zeros(rate * 2, dtype=np.float64)
        length = int(rate * 0.15)
        phase = np.arange(length) / rate
        pip = np.sin(2 * np.pi * 880 * phase) * np.hanning(length) * 0.7
        for offset in (0, int(rate * 0.3)):
            samples[offset : offset + length] = pip
        pcm = np.repeat((samples * 32767).astype(np.int16)[:, None], channels, axis=1)
        self._sound = pygame.mixer.Sound(buffer=pcm.tobytes())
        self._sound.set_volume(self.volume)
        self._channel = self._sound.play(loops=-1, maxtime=round(self.duration * 1000))
        if self._channel is None:
            raise RuntimeError("No timer alert channel available")
        self._timer_ids = {timer["timer_id"] for timer in timers}
        self.duck_music(True)

    def remove(self, timer_id: str) -> None:
        self._timer_ids.discard(timer_id)
        if not self._timer_ids:
            self.hush()

    @property
    def is_ringing(self) -> bool:
        return self._channel is not None

    def update(self) -> bool:
        if self._channel is not None and not self._channel.get_busy():
            self.hush()
        return self.is_ringing

    def hush(self) -> None:
        """Never pause/resume music: restoring volume preserves explicit user intent."""
        try:
            if self._channel is not None:
                self._channel.stop()
        except pygame.error:
            logging.getLogger(__name__).warning("Timer output device is unavailable", exc_info=True)
        finally:
            self._channel = self._sound = None
            self._timer_ids.clear()
            self.duck_music(False)
