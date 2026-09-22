#!/usr/bin/env bash

# Realtime Smart Voice Assistant runner.
# Bootstraps local dependencies, validates config, then starts the assistant.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SETUP_ONLY=false
ASSISTANT_ARGS=()
PYTHON_BIN="python3.12"
for arg in "$@"; do
    case "$arg" in
        --setup-only)
            SETUP_ONLY=true
            ;;
        *)
            ASSISTANT_ARGS+=("$arg")
            ;;
    esac
done

log_info() {
    echo -e "${YELLOW}$1${NC}"
}

log_ok() {
    echo -e "${GREEN}$1${NC}"
}

log_err() {
    echo -e "${RED}$1${NC}"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

compute_sha256() {
    local file="$1"
    if command_exists shasum; then
        shasum -a 256 "$file" | awk '{print $1}'
    elif command_exists sha256sum; then
        sha256sum "$file" | awk '{print $1}'
    else
        openssl dgst -sha256 "$file" | awk '{print $2}'
    fi
}

echo -e "${BLUE}=== Realtime Smart Voice Assistant ===${NC}"

if ! command_exists "$PYTHON_BIN"; then
    log_err "ERROR: Python 3.12 is required but not found."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Install it with: brew install python@3.12"
    else
        echo "Install Python 3.12 and its venv support using your package manager."
    fi
    exit 1
fi

# Check for system dependencies
if [[ "$OSTYPE" == "darwin"* ]]; then
    log_info "Checking macOS dependencies..."

    if ! command_exists brew; then
        log_err "ERROR: Homebrew is required on macOS to install dependencies."
        echo "Install Homebrew from: https://brew.sh/"
        exit 1
    fi

    if ! brew list portaudio &>/dev/null; then
        log_info "Installing PortAudio..."
        brew install portaudio
        log_ok "PortAudio installed."
    fi

    if ! command_exists ffmpeg; then
        log_info "Installing FFmpeg..."
        brew install ffmpeg
        log_ok "FFmpeg installed."
    fi

elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    log_info "Checking Linux dependencies..."

    if command_exists apt-get; then
        if ! dpkg -s portaudio19-dev >/dev/null 2>&1; then
            log_info "Installing system dependencies via apt..."
            sudo apt-get update
            sudo apt-get install -y portaudio19-dev python3-pyaudio python3-pip python3-venv ffmpeg
            log_ok "System dependencies installed."
        fi

        if ! command_exists ffmpeg; then
            log_info "Installing FFmpeg via apt..."
            sudo apt-get install -y ffmpeg
            log_ok "FFmpeg installed."
        fi
    else
        log_info "Non-apt Linux detected. Please ensure PortAudio and FFmpeg are installed."
    fi
fi

if [[ ! -d "venv" ]]; then
    log_info "Creating virtual environment..."
    "$PYTHON_BIN" -m venv venv
else
    VENV_PYTHON_VERSION="$(venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    if [[ "$VENV_PYTHON_VERSION" != "3.12" ]]; then
        log_err "ERROR: Existing venv uses Python ${VENV_PYTHON_VERSION:-unknown}; Python 3.12 is required."
        echo "Move the existing venv aside and rerun setup:"
        echo "  mv venv venv-backup"
        echo "  ./run.sh --setup-only"
        exit 1
    fi
fi

# shellcheck disable=SC1091
source venv/bin/activate
log_ok "Virtual environment ready."

REQ_HASH_FILE="venv/.requirements.sha256"
CURRENT_REQ_HASH="$(compute_sha256 requirements.txt)"
SAVED_REQ_HASH=""
if [[ -f "$REQ_HASH_FILE" ]]; then
    SAVED_REQ_HASH="$(cat "$REQ_HASH_FILE")"
fi

if [[ "$CURRENT_REQ_HASH" != "$SAVED_REQ_HASH" ]]; then
    log_info "Installing/updating Python dependencies..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    printf '%s' "$CURRENT_REQ_HASH" > "$REQ_HASH_FILE"
    log_ok "Dependencies installed."
else
    log_ok "Dependencies already up-to-date."
fi

if [[ "$SETUP_ONLY" == "true" ]]; then
    log_info "Preparing offline wake-word model..."
    python src/wake_word_model.py
    log_ok "Setup complete."
    exit 0
fi

# Python parses .env without executing it and validates the selected --config.
# Environment-only keys work without a .env file.
if [[ ! -f ".env" && -f ".env.example" && -z "${OPENAI_API_KEY:-}" ]]; then
    (umask 077; cp .env.example .env)
    log_info "Created .env template; add OPENAI_API_KEY if it is not in your config."
fi

log_ok "Starting Realtime Voice Assistant..."
if [[ ${#ASSISTANT_ARGS[@]} -gt 0 ]]; then
    exec python src/realtime_voice_assistant.py "${ASSISTANT_ARGS[@]}"
else
    exec python src/realtime_voice_assistant.py
fi
