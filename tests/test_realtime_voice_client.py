import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

sys.modules.setdefault("pyaudio", types.SimpleNamespace())
sys.modules.setdefault("websockets", types.SimpleNamespace())

if "music_commands" not in sys.modules:
    music_commands = types.ModuleType("music_commands")
    music_commands.MusicCommandHandler = object
    sys.modules["music_commands"] = music_commands

RealtimeVoiceClient = importlib.import_module("realtime_voice_client").RealtimeVoiceClient


def test_default_realtime_model_matches_current_generation():
    assert RealtimeVoiceClient.DEFAULT_REALTIME_MODEL == "gpt-realtime-2.1"


def test_calculate_rms_handles_full_scale_pcm16_without_overflow():
    samples = np.array([32767, -32768], dtype=np.int16)

    rms = RealtimeVoiceClient._calculate_rms(samples.tobytes())

    assert rms == pytest.approx(32767.5, abs=0.5)


def test_calculate_rms_returns_zero_for_empty_audio():
    assert RealtimeVoiceClient._calculate_rms(b"") == 0.0
