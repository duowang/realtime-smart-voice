import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def detector_module(monkeypatch, tmp_path):
    audio = Mock()
    spotter = Mock()
    spotter.is_ready.return_value = False
    keyword_files = []

    def create_spotter(**kwargs):
        keyword_files.append(Path(kwargs["keywords_file"]).read_text())
        return spotter

    monkeypatch.setitem(
        sys.modules,
        "pyaudio",
        types.SimpleNamespace(
            PyAudio=Mock(return_value=audio),
            paInt16=8,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "sherpa_onnx",
        types.SimpleNamespace(
            KeywordSpotter=Mock(side_effect=create_spotter),
        ),
    )
    tokenizer = Mock()
    tokenizer.encode.side_effect = lambda text, out_type: {
        "HI TACO": ["▁HI", "▁TA", "CO"],
        "HELLO": ["▁HELLO"],
    }.get(text, ["<unk>"])
    monkeypatch.setitem(
        sys.modules,
        "sentencepiece",
        types.SimpleNamespace(
            SentencePieceProcessor=Mock(return_value=tokenizer),
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "tested_wake_detector", SRC_DIR / "wake_word_detector.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tokenizer_path = tmp_path / "bpe.model"
    paths = {name: tmp_path / name for name in ("encoder", "decoder", "joiner", "tokens")}
    paths["tokenizer"] = tokenizer_path
    monkeypatch.setattr(module, "ensure_wake_word_model", Mock(return_value=paths))
    return module, audio, spotter, keyword_files, tokenizer


def test_phrases_use_model_tokenizer_and_safe_result_labels(detector_module):
    module, _, _, files, tokenizer = detector_module
    detector = module.WakeWordDetector({"wake_keywords": ["  Hi   Taco ", "Hello"]})
    assert files == ["▁HI ▁TA CO @wake_0\n▁HELLO @wake_1\n"]
    assert [c.args[0] for c in tokenizer.encode.call_args_list] == ["HI TACO", "HELLO"]
    assert detector._keyword_labels == {"wake_0": "Hi Taco", "wake_1": "Hello"}


def test_incomplete_tokenization_is_rejected_before_native_initialization(detector_module):
    module, _, _, _, tokenizer = detector_module
    tokenizer.encode.side_effect = None
    tokenizer.encode.return_value = []
    with pytest.raises(ValueError, match="Cannot tokenize"):
        module.WakeWordDetector({})
    module.sherpa_onnx.KeywordSpotter.assert_not_called()


@pytest.mark.parametrize("phrases", [[], "Hi Taco", ["Hi/Taco"], ["Unknown"], [123]])
def test_invalid_phrases_fail_before_opening_audio(detector_module, phrases):
    module, _, _, _, _ = detector_module
    with pytest.raises(ValueError):
        module.WakeWordDetector({"wake_keywords": phrases})
    module.pyaudio.PyAudio.assert_not_called()
    module.sherpa_onnx.KeywordSpotter.assert_not_called()


@pytest.mark.parametrize("threshold", [0, -0.1, 1.1, float("nan")])
def test_invalid_threshold_fails_before_downloading(detector_module, threshold):
    module, _, _, _, _ = detector_module
    with pytest.raises(ValueError, match="wake_word_threshold"):
        module.WakeWordDetector({"wake_word_threshold": threshold})
    module.ensure_wake_word_model.assert_not_called()


@pytest.mark.parametrize("boost", [0, 0.5, 9, float("nan"), "4", True])
def test_invalid_input_boost_fails_before_downloading(detector_module, boost):
    module, _, _, _, _ = detector_module
    with pytest.raises(ValueError, match="wake_word_input_boost"):
        module.WakeWordDetector({"wake_word_input_boost": boost})
    module.ensure_wake_word_model.assert_not_called()


def test_pcm_uses_original_and_clipped_boosted_decoder_histories(detector_module):
    module, _, spotter, _, _ = detector_module
    detector = module.WakeWordDetector({})
    original, boosted = Mock(), Mock()
    spotter.create_stream.side_effect = [original, boosted]
    pcm = np.array([-32768, -4096, 0, 4096, 32767], dtype=np.int16)
    assert detector.process_audio(pcm.tobytes()) is None
    raw_rate, raw_samples = original.accept_waveform.call_args.args
    boosted_rate, boosted_samples = boosted.accept_waveform.call_args.args
    assert raw_rate == boosted_rate == 16000
    assert raw_samples.dtype == boosted_samples.dtype == np.float32
    np.testing.assert_array_equal(raw_samples, [-1, -0.125, 0, 0.125, 32767 / 32768])
    np.testing.assert_array_equal(boosted_samples, [-1, -0.5, 0, 0.5, 1])


def test_boost_can_be_disabled(detector_module):
    module, _, spotter, _, _ = detector_module
    detector = module.WakeWordDetector({"wake_word_input_boost": 1})
    detector.process_audio(np.zeros(512, dtype=np.int16).tobytes())
    spotter.create_stream.assert_called_once()
    assert detector.boosted_keyword_stream is None


def test_boosted_decoder_can_detect_when_original_does_not(detector_module):
    module, _, spotter, _, _ = detector_module
    detector = module.WakeWordDetector({})
    original, boosted = Mock(), Mock()
    spotter.create_stream.side_effect = [original, boosted]
    spotter.is_ready.side_effect = [True, False, True]
    spotter.get_result.side_effect = ["", "wake_0"]

    assert detector.process_audio(np.zeros(512, dtype=np.int16).tobytes()) == "Hi Taco"
    assert [call.args[0] for call in spotter.reset_stream.call_args_list] == [
        original, boosted
    ]


def test_detection_releases_microphone_and_restarts_with_fresh_decoder(detector_module):
    module, audio, spotter, _, _ = detector_module
    detector = module.WakeWordDetector({})
    old_decoder, old_boosted, new_decoder, new_boosted = Mock(), Mock(), Mock(), Mock()
    spotter.create_stream.side_effect = [
        old_decoder, old_boosted, new_decoder, new_boosted
    ]
    spotter.is_ready.return_value = True
    spotter.get_result.return_value = "wake_0"
    old_microphone = Mock()
    old_microphone.read.return_value = np.zeros(512, dtype=np.int16).tobytes()
    audio.open.side_effect = [old_microphone, Mock()]

    assert asyncio.run(detector.listen_for_wake_word()) == "Hi Taco"
    assert [call.args[0] for call in spotter.reset_stream.call_args_list] == [
        old_decoder, old_boosted
    ]
    old_microphone.stop_stream.assert_called_once()
    old_microphone.close.assert_called_once()
    assert not detector.is_listening
    assert detector.keyword_stream is None
    assert detector.boosted_keyword_stream is None

    asyncio.run(detector.start_listening())
    assert detector.is_listening
    assert detector.keyword_stream is new_decoder
    assert detector.boosted_keyword_stream is new_boosted
    detector.cleanup()
    detector.cleanup()
    audio.terminate.assert_called_once()


def test_cleanup_closes_audio_even_if_stop_fails(detector_module):
    module, audio, _, _, _ = detector_module
    detector = module.WakeWordDetector({})
    asyncio.run(detector.start_listening())
    microphone = detector.stream
    microphone.stop_stream.side_effect = OSError("device disconnected")
    detector.cleanup()
    microphone.close.assert_called_once()
    audio.terminate.assert_called_once()
    assert not detector.is_listening
