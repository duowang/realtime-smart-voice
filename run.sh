#!/bin/bash

# Realtime Smart Voice Assistant Runner
# This script sets up the environment and runs the realtime voice assistant

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Realtime Smart Voice Assistant ===${NC}"

# Check for system dependencies
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS dependencies
    echo -e "${YELLOW}Checking macOS dependencies...${NC}"
    
    # Check if PortAudio is installed (required for PyAudio on macOS)
    if ! brew list portaudio &>/dev/null; then
        echo -e "${YELLOW}Installing PortAudio (required for PyAudio on macOS)...${NC}"
        if ! command -v brew &> /dev/null; then
            echo -e "${RED}ERROR: Homebrew is required on macOS to install PortAudio${NC}"
            echo -e "Install Homebrew from: https://brew.sh/"
            exit 1
        fi
        brew install portaudio
        echo -e "${GREEN}PortAudio installed successfully${NC}"
    fi
    
    # Check if ffmpeg is installed (required for YouTube Music playback)
    if ! command -v ffmpeg &> /dev/null; then
        echo -e "${YELLOW}Installing FFmpeg (required for YouTube Music playback)...${NC}"
        brew install ffmpeg
        echo -e "${GREEN}FFmpeg installed successfully${NC}"
    fi
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux dependencies
    echo -e "${YELLOW}Checking Linux dependencies...${NC}"
    
    # Check if portaudio is installed
    if ! dpkg -l | grep -q portaudio19-dev 2>/dev/null; then
        echo -e "${YELLOW}Installing system dependencies...${NC}"
        sudo apt update
        sudo apt install -y portaudio19-dev python3-pyaudio python3-pip python3-venv ffmpeg
        echo -e "${GREEN}System dependencies installed successfully${NC}"
    fi
    
    # Check if ffmpeg is installed
    if ! command -v ffmpeg &> /dev/null; then
        echo -e "${YELLOW}Installing FFmpeg...${NC}"
        sudo apt install -y ffmpeg
        echo -e "${GREEN}FFmpeg installed successfully${NC}"
    fi
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Check if requirements are installed
if [ ! -f "venv/.requirements_installed" ]; then
    echo -e "${YELLOW}Installing requirements...${NC}"
    pip install --upgrade pip
    pip install -r requirements.txt
    touch venv/.requirements_installed
    echo -e "${GREEN}Requirements installed successfully${NC}"
else
    echo -e "${GREEN}Requirements already installed${NC}"
fi

# Check if .env file exists, if not suggest creating one
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}No .env file found. Creating one from template...${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}Please edit .env file and add your API keys:${NC}"
        echo -e "${YELLOW}  - OPENAI_API_KEY (get from: https://platform.openai.com/api-keys)${NC}"
        echo -e "${YELLOW}  - PORCUPINE_ACCESS_KEY (get from: https://console.picovoice.ai/)${NC}"
        echo -e "${RED}Exiting - please configure .env file first${NC}"
        exit 1
    fi
fi

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo -e "${GREEN}Loaded environment variables from .env${NC}"
fi

# Check for required API keys (from .env, environment, or config.json)
if [ -z "$OPENAI_API_KEY" ] && ! grep -q "openai_api_key" config/config.json 2>/dev/null; then
    echo -e "${RED}ERROR: OpenAI API key is required${NC}"
    echo -e "Add OPENAI_API_KEY to .env file, set as environment variable, or add 'openai_api_key' to config/config.json"
    echo -e "Get from: https://platform.openai.com/api-keys"
    exit 1
fi

if [ -z "$PORCUPINE_ACCESS_KEY" ] && ! grep -q "porcupine_access_key" config/config.json 2>/dev/null; then
    echo -e "${RED}ERROR: Porcupine access key is required${NC}"
    echo -e "Add PORCUPINE_ACCESS_KEY to .env file, set as environment variable, or add 'porcupine_access_key' to config/config.json"
    echo -e "Get a free key from: https://console.picovoice.ai/"
    exit 1
fi

# Check if Hi Taco wake word file exists (platform-specific)
PLATFORM_SUFFIX=""
if [[ "$OSTYPE" == "darwin"* ]]; then
    if [[ "$(uname -m)" == "arm64" ]]; then
        PLATFORM_SUFFIX="mac_apple"
    else
        PLATFORM_SUFFIX="mac"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if [[ $(uname -m) =~ ^(arm|aarch64) ]]; then
        PLATFORM_SUFFIX="raspberry-pi"
    else
        PLATFORM_SUFFIX="linux-x86_64"
    fi
else
    PLATFORM_SUFFIX="raspberry-pi"  # fallback
fi

# Try platform-specific file first, then fallback
WAKE_WORD_FILES=(
    "Hi-Taco_en_${PLATFORM_SUFFIX}_v3_0_0.ppn"
    "Hi-Taco_en_raspberry-pi_v3_0_0.ppn"
)

WAKE_WORD_FOUND=false
for file in "${WAKE_WORD_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}Found wake word file: $file${NC}"
        WAKE_WORD_FOUND=true
        break
    fi
done

if [ "$WAKE_WORD_FOUND" = false ]; then
    echo -e "${RED}ERROR: Hi Taco wake word file not found${NC}"
    echo -e "Expected for your platform ($PLATFORM_SUFFIX): Hi-Taco_en_${PLATFORM_SUFFIX}_v3_0_0.ppn"
    echo -e "Or fallback: Hi-Taco_en_raspberry-pi_v3_0_0.ppn"
    echo -e "Please download the correct .ppn file for your platform and place it in the project root directory"
    exit 1
fi

echo -e "${GREEN}Starting Realtime Voice Assistant with YouTube Music support...${NC}"
echo -e "${YELLOW}Say 'Hi Taco' to start a conversation${NC}"
echo -e "${YELLOW}Music commands: 'play [song]', 'pause', 'resume', 'stop music'${NC}"
echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
echo ""

# Run the assistant
cd src
python realtime_voice_assistant.py "$@"