import importlib
import sys
import types
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

for module_name in ("pyaudio", "soundfile", "websockets"):
    sys.modules.setdefault(module_name, types.SimpleNamespace())

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda path: None
sys.modules.setdefault("dotenv", dotenv)

for module_name, class_name in (
    ("wake_word_detector", "WakeWordDetector"),
    ("music_commands", "MusicCommandHandler"),
):
    module = types.ModuleType(module_name)
    setattr(module, class_name, object)
    sys.modules.setdefault(module_name, module)

assistant_module = importlib.import_module("realtime_voice_assistant")
DEFAULT_CONFIG_FILE = assistant_module.DEFAULT_CONFIG_FILE
RealtimeVoiceAssistant = assistant_module.RealtimeVoiceAssistant


def test_default_config_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assistant = object.__new__(RealtimeVoiceAssistant)
    config = assistant._load_config(DEFAULT_CONFIG_FILE)

    assert Path(DEFAULT_CONFIG_FILE) == PROJECT_ROOT / "config" / "config.json"
    assert config["realtime_model"] == "gpt-realtime-2.1"
