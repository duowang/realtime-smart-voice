"""Prepare assets, change the wake phrase, or check setup without opening audio."""

import argparse
import importlib
import json
import os
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = (
    "dotenv",
    "pyaudio",
    "numpy",
    "soundfile",
    "sherpa_onnx",
    "sentencepiece",
    "websockets",
    "ytmusicapi",
    "yt_dlp",
    "pygame",
    "requests",
    "PIL",
    "openai",
)


def report(ok: bool, description: str, fix: str = "") -> bool:
    print(f"[{'OK' if ok else 'FIX'}] {description}")
    if not ok and fix:
        print(f"      {fix}")
    return ok


def check_dependencies() -> bool:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    missing = []
    for name in DEPENDENCIES:
        try:
            importlib.import_module(name)
        except (ImportError, OSError):
            missing.append(name)
    return report(
        not missing,
        "Python dependencies load" if not missing else f"Cannot load: {', '.join(missing)}",
        "Run venv/bin/python -m pip install -r requirements.txt; check system audio libraries.",
    )


def create_env_template() -> bool:
    """Create once with owner-only access; never truncate an existing file/symlink."""
    template = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    try:
        descriptor = os.open(PROJECT_ROOT / ".env", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(template)
    print("Created .env. Open it in your editor and replace the OPENAI_API_KEY placeholder.")
    return True


def model_directory(config: dict) -> Path:
    from wake_word_model import DEFAULT_MODEL_DIR

    path = Path(config.get("wake_word_model_dir", DEFAULT_MODEL_DIR)).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def key_configured(config: dict) -> bool:
    from configuration import get_api_key

    try:
        get_api_key(config)
    except ValueError:
        return False
    return True


def prepare(config: dict, config_path: Path) -> int:
    from configuration import default_config_path
    from wake_word_model import ensure_wake_word_model

    if not key_configured(config):
        create_env_template()
    print("Preparing the offline wake-word model (downloads once, about 18 MB)...")
    ensure_wake_word_model(model_directory(config))
    print("Setup complete. No audio devices were opened.")
    command = "./run.sh"
    if config_path.resolve() != default_config_path().resolve():
        command += f" --config {shlex.quote(str(config_path))}"
    if key_configured(config):
        print(f"Next: {command}")
    else:
        print(f"Next: add your OpenAI API key to .env, then run {command}.")
    return 0


def set_wake_word(phrase: str, config_path: Path | None = None) -> int:
    """Validate before atomically saving; never initialize the detector or audio."""
    from configuration import load_config, normalize_wake_phrase
    from wake_word_detector import encode_keywords
    from wake_word_model import ensure_wake_word_model

    phrase = normalize_wake_phrase(phrase)
    target = (
        config_path.expanduser() if config_path is not None else PROJECT_ROOT / "config/local.json"
    )
    source = (
        target
        if config_path is not None or target.exists()
        else PROJECT_ROOT / "config/config.json"
    )
    config = load_config(source)
    paths = ensure_wake_word_model(model_directory(config))
    encode_keywords([phrase], paths["tokenizer"])
    config["wake_keywords"] = [phrase]
    # Write alongside the destination so a failed write cannot leave partial JSON.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=".wake-config-", delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(config, output, indent=2, ensure_ascii=False)
            output.write("\n")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f'Wake phrase saved: "{phrase}" ({target})')
    command = "./run.sh"
    if config_path is not None:
        command += f" --config {shlex.quote(str(config_path))}"
    print(f"Next: {command}. If the assistant is running, stop it with Ctrl+C first.")
    print("No training or calibration required. No audio devices were opened.")
    return 0


def diagnose(config: dict) -> int:
    from wake_word_model import MODEL_FILES

    checks = [check_dependencies()]
    checks.append(
        report(
            bool(shutil.which("ffmpeg")),
            "FFmpeg available",
            "Install FFmpeg using your system package manager.",
        )
    )
    for name in ("hi_there.wav", "bye_bye.wav"):
        path = PROJECT_ROOT / "audio" / name
        checks.append(
            report(
                path.is_file() and path.stat().st_size > 0,
                f"Prompt: {name}",
                "Restore the audio/ files from the repository.",
            )
        )
    model = model_directory(config)
    complete = all(
        (model / name).is_file() and (model / name).stat().st_size > 0
        for name in MODEL_FILES.values()
    )
    checks.append(
        report(
            complete, f"Wake model: {model}", "Run ./run.sh --setup-only with the same --config."
        )
    )
    checks.append(
        report(
            key_configured(config),
            "OpenAI API key configured (not checked with OpenAI)",
            "Edit .env and set OPENAI_API_KEY, or export it in your shell.",
        )
    )
    print(
        "No network calls or audio devices used. Microphone permissions and API access are checked when you run the assistant."
    )
    return 0 if all(checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--prepare", action="store_true", help="Prepare .env and download missing model files"
    )
    mode.add_argument(
        "--wake-word", metavar="PHRASE", help="Save a new English wake phrase and exit"
    )
    parser.add_argument(
        "--config", type=Path, help="Use a specific JSON config instead of personal settings"
    )
    args = parser.parse_args()
    if not report(
        sys.version_info[:2] == (3, 12), "Python 3.12", "Recreate venv with ./run.sh --setup-only."
    ):
        return 1
    try:
        from configuration import default_config_path, load_config

        if args.wake_word is not None:
            return set_wake_word(args.wake_word, args.config)
        config_path = args.config or default_config_path()
        config = load_config(config_path)
        report(True, f"Configuration: {config_path}")
        if args.prepare:
            if not check_dependencies():
                return 1
            return prepare(config, config_path)
        return diagnose(config)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        print(f"[FIX] {error}")
        if args.wake_word is None:
            print("See README.md for setup instructions, then rerun ./run.sh --setup-only.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
