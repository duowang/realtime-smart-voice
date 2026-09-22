#!/usr/bin/env bash
# Set up a local Python environment, or start the assistant from an existing one.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
    cat <<'HELP'
Usage: ./run.sh [--setup-only | --doctor | --wake-word "PHRASE"] [--config PATH]

  (no option)     Set up if needed, then listen for your wake phrase ("Hi Taco" by default).
  --setup-only   Install dependencies, prepare the wake model and create .env.
                 Does not start audio or require an OpenAI API key.
  --doctor       Check this installation without downloads or audio devices.
  --wake-word PHRASE
                 Save a new English wake phrase and exit, e.g. --wake-word "Hey Nova".
                 Uses config/local.json unless --config is specified. No API key needed.
  --config PATH  Use another JSON config (relative to the repository root).
                 By default, use config/local.json if present, else config/config.json.
  -h, --help     Show this help without installing anything.

First time: follow the system prerequisites in README.md, then:
  ./run.sh --setup-only
  # Edit .env and add your OpenAI API key.
  ./run.sh
HELP
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
command_exists() { command -v "$1" >/dev/null 2>&1; }

MODE=run
CONFIG_FILE=config/config.json
[[ ! -e config/local.json ]] || CONFIG_FILE=config/local.json
CONFIG_EXPLICIT=false
WAKE_WORD=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --setup-only|--doctor)
            [[ "$MODE" == run ]] || fail "Choose only one of --setup-only, --doctor or --wake-word."
            MODE="${1#--}"
            shift
            ;;
        --wake-word)
            [[ "$MODE" == run ]] || fail "Choose only one of --setup-only, --doctor or --wake-word."
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail '--wake-word needs a phrase in quotes, e.g. --wake-word "Hey Nova".'
            MODE=wake-word
            WAKE_WORD="$2"
            shift 2
            ;;
        --config)
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail "--config needs a file path."
            CONFIG_FILE="$2"
            CONFIG_EXPLICIT=true
            shift 2
            ;;
        --config=*) CONFIG_FILE="${1#--config=}"; CONFIG_EXPLICIT=true; shift ;;
        *) fail "Unknown option: $1. Run ./run.sh --help." ;;
    esac
done
[[ -f "$CONFIG_FILE" ]] || fail "Config not found: $CONFIG_FILE"

check_venv() {
    local version
    version="$(venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    [[ "$version" == 3.12 ]] || fail "The existing venv uses Python ${version:-unknown}; 3.12 is required. Move venv aside, then run ./run.sh --setup-only."
}

# This path is deliberately read-only, even on an incomplete installation.
if [[ "$MODE" == doctor ]]; then
    [[ -x venv/bin/python ]] || fail "No usable venv. Run ./run.sh --setup-only first."
    check_venv
    export PYTHONDONTWRITEBYTECODE=1
    exec venv/bin/python src/setup_assistant.py --config "$CONFIG_FILE"
fi

case "$(uname -s)" in
    Darwin|Linux) ;;
    *) fail "The runner supports macOS and Linux. See README.md for prerequisites." ;;
esac

SYSTEM_DEPS_READY=false
install_system_deps() {
    [[ "$SYSTEM_DEPS_READY" == false ]] || return 0
    if [[ "$(uname -s)" == Darwin ]]; then
        command_exists brew || fail "Install Homebrew from https://brew.sh, then: brew install uv portaudio ffmpeg"
        local packages=()
        brew list portaudio >/dev/null 2>&1 || packages+=(portaudio)
        command_exists ffmpeg || packages+=(ffmpeg)
        if [[ ${#packages[@]} -gt 0 ]]; then
            brew install "${packages[@]}"
        fi
        # Managed Python also needs Homebrew's headers when building PyAudio.
        local portaudio_prefix
        portaudio_prefix="$(brew --prefix portaudio)"
        export CFLAGS="-I${portaudio_prefix}/include ${CFLAGS:-}"
        export LDFLAGS="-L${portaudio_prefix}/lib ${LDFLAGS:-}"
    elif command_exists apt-get && command_exists dpkg-query; then
        local packages=() package status
        for package in portaudio19-dev libsndfile1 ffmpeg build-essential pkg-config; do
            status="$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)"
            [[ "$status" == 'install ok installed' ]] || packages+=("$package")
        done
        if [[ ${#packages[@]} -gt 0 ]]; then
            local privilege=()
            if [[ "$EUID" -ne 0 ]]; then
                command_exists sudo || fail "Ask an administrator to install: ${packages[*]}"
                privilege=(sudo)
            fi
            "${privilege[@]}" apt-get update
            "${privilege[@]}" apt-get install -y "${packages[@]}"
        fi
    else
        printf '%s\n' "Ensure PortAudio development headers, libsndfile, a C compiler and FFmpeg are installed (see README.md)."
    fi
    command_exists ffmpeg || fail "FFmpeg is missing. Install it using your system package manager."
    SYSTEM_DEPS_READY=true
}

# Existing environments work without uv or a separately discoverable python3.12.
if [[ -e venv || -L venv ]]; then
    check_venv
else
    UV_BIN="$(command -v uv || true)"
    if [[ -z "$UV_BIN" && -x "${HOME}/.local/bin/uv" ]]; then
        UV_BIN="${HOME}/.local/bin/uv"
    fi
    [[ -n "$UV_BIN" ]] || command_exists python3.12 || fail "Install uv (https://docs.astral.sh/uv/getting-started/installation/) or Python 3.12, then rerun this command."
    install_system_deps
    printf '%s\n' 'Creating the Python 3.12 environment...'
    if [[ -n "$UV_BIN" ]]; then
        "$UV_BIN" venv --python 3.12 --managed-python --seed venv
    else
        python3.12 -m venv venv || fail "Python 3.12 needs venv support. On Ubuntu: sudo apt-get install python3.12-venv python3.12-dev. Alternatively install uv, move the incomplete venv aside, and retry."
    fi
    check_venv
fi

REQ_HASH_FILE=venv/.requirements.sha256
PREPARE_ASSETS=false
CURRENT_REQ_HASH="$(venv/bin/python -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest())')"
SAVED_REQ_HASH=""
[[ ! -f "$REQ_HASH_FILE" ]] || SAVED_REQ_HASH="$(cat "$REQ_HASH_FILE")"

if [[ "$CURRENT_REQ_HASH" != "$SAVED_REQ_HASH" || "$MODE" == setup-only ]]; then
    install_system_deps
    printf '%s\n' 'Installing Python dependencies...'
    # A failed repair must not leave a stamp that makes the next launch skip it.
    rm -f "$REQ_HASH_FILE"
    if ! venv/bin/python -m pip --version >/dev/null 2>&1; then
        venv/bin/python -m ensurepip --upgrade
    fi
    venv/bin/python -m pip install --upgrade pip
    venv/bin/python -m pip install -r requirements.txt
    venv/bin/python -m pip check
    printf '%s' "$CURRENT_REQ_HASH" > "$REQ_HASH_FILE"
    PREPARE_ASSETS=true
fi

if [[ "$MODE" == wake-word ]]; then
    if [[ "$CONFIG_EXPLICIT" == true ]]; then
        exec venv/bin/python src/setup_assistant.py --wake-word "$WAKE_WORD" --config "$CONFIG_FILE"
    fi
    exec venv/bin/python src/setup_assistant.py --wake-word "$WAKE_WORD"
fi

if [[ "$MODE" == setup-only ]]; then
    install_system_deps
    exec venv/bin/python src/setup_assistant.py --prepare --config "$CONFIG_FILE"
fi

# A fresh install also prepares assets when launched without --setup-only.
if [[ "$PREPARE_ASSETS" == true ]]; then
    venv/bin/python src/setup_assistant.py --prepare --config "$CONFIG_FILE"
fi
printf '%s\n' 'Starting the assistant. Press Ctrl+C to stop.'
exec venv/bin/python src/realtime_voice_assistant.py --config "$CONFIG_FILE"
