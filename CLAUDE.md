# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a real-time smart voice assistant that combines:
- **Picovoice Porcupine** for wake word detection (offline, real-time)
- **OpenAI Realtime API** (GA) for natural voice conversations via direct WebSocket
- **Asynchronous Architecture** for responsive, non-blocking audio processing

## Key Features

This project provides a modern real-time voice assistant with:
- **Real-time Processing**: Uses OpenAI Realtime API for immediate voice interactions
- **Streaming Audio**: Continuous bidirectional audio streams for natural conversation
- **Low Latency**: Real-time conversation without delays of traditional STT→LLM→TTS pipelines
- **Music Playback**: YouTube Music integration with voice commands (play, pause, resume, skip)
- **Album Art Display**: Song thumbnails rendered in terminal using ANSI true-color half-block characters
- **Asynchronous**: Non-blocking architecture using asyncio throughout

## Development Commands

### Environment Setup
```bash
# Install system dependencies (Linux/Raspberry Pi)
sudo apt install -y portaudio19-dev python3-pyaudio python3-pip python3-venv

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Main way to run (with environment setup and validation)
./run.sh

# Direct execution
cd src && python realtime_voice_assistant.py

# With custom config
./run.sh --config /path/to/config.json
```

### Testing Components
```bash
# Test wake word detection only
cd src && python -c "import asyncio; from wake_word_detector import WakeWordDetector; asyncio.run(WakeWordDetector({}).listen_for_wake_word())"

# Test audio devices
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)}') for i in range(p.get_device_count())]"

# Test microphone
arecord -d 5 test.wav && aplay test.wav
```

## Architecture Overview

### Core Components

1. **RealtimeVoiceAssistant** (`realtime_voice_assistant.py`) - Main orchestrator
   - Manages the complete application lifecycle
   - Coordinates wake word detection and real-time conversation
   - Handles asynchronous event loop and signal management
   - Provides comprehensive logging and error handling

2. **WakeWordDetector** (`wake_word_detector.py`) - Wake word detection
   - Asynchronous Picovoice Porcupine integration
   - Custom "Hi Taco" wake word with .ppn file
   - PyAudio-based continuous audio monitoring
   - High sensitivity (0.9) for responsive detection

3. **RealtimeVoiceClient** (`realtime_voice_client.py`) - Real-time conversation
   - Direct WebSocket connection to OpenAI Realtime API (GA)
   - Real-time bidirectional audio streaming (PCM 24kHz)
   - Server-side Voice Activity Detection (server_vad)
   - Barge-in support (user can interrupt assistant)
   - Music command detection and routing

4. **MusicCommandHandler** (`music_commands.py`) - Music playback
   - YouTube Music search and playback via yt-dlp
   - Voice commands: play, pause, resume, stop, next, etc.
   - Auto-pause during conversation, auto-resume after

5. **YouTubeMusicPlayer** (`youtube_music_player.py`) - Audio player
   - Direct yt-dlp download and pygame playback
   - Queue management and playback controls
   - Thumbnail download and caching (hi-res via Google CDN URL rewrite)
   - Terminal album art rendering using ANSI true-color half-block characters
   - Adaptive sizing based on terminal dimensions (50% of smaller axis)

### Data Flow
1. **Continuous Wake Word Monitoring**: Asynchronous audio monitoring for "Hi Taco"
2. **Wake Word Detection**: Porcupine processes audio frames in real-time
3. **Conversation Initialization**: WebSocket connection established to Realtime API
4. **Real-time Audio Streaming**: Bidirectional audio with OpenAI Realtime API
5. **Natural Conversation**: Low-latency back-and-forth interaction
6. **Automatic Timeout**: Return to wake word detection after inactivity

### Configuration System

Main config: `config/config.json`
- API keys (OpenAI Realtime API, Porcupine)
- Conversation timeout settings
- Wake word configuration
- Logging preferences

Environment Variables (.env file):
- `OPENAI_API_KEY` - Required for Realtime API access
- `PORCUPINE_ACCESS_KEY` - Required for wake word detection
- `CONVERSATION_TIMEOUT` - Optional conversation timeout (default: 30)
- `LOG_LEVEL` - Optional logging level (default: INFO)

The project supports `.env` files for secure API key management with automatic loading via python-dotenv.

### Custom Wake Word

Uses a custom "Hi Taco" wake word:
- File: `Hi-Taco_en_raspberry-pi_v3_0_0.ppn` and `Hi-Taco_en_mac_v3_0_0.ppn`
- High sensitivity (0.9) for fastest detection
- Asynchronous processing to avoid blocking

### OpenAI Realtime API Integration

This project uses OpenAI's Realtime API (GA, not beta):
- **Endpoint**: `wss://api.openai.com/v1/realtime`
- **Model**: `gpt-realtime` (configurable via `realtime_model` in config)
- **Voice**: `alloy` (configurable)
- **Connection**: Direct WebSocket via `websockets` library (no Pipecat)
- **Audio Format**: PCM 24kHz, mono, 16-bit
- **VAD**: Server-side voice activity detection (`server_vad`)
- **Transcription**: `gpt-4o-mini-transcribe` for input audio transcription
- **Session Config**: Uses GA API format with nested `audio.input`/`audio.output` objects

### Asynchronous Architecture

Built entirely on asyncio for maximum responsiveness:
- **Non-blocking Audio**: Continuous wake word monitoring
- **Concurrent Processing**: Wake word detection + real-time conversation
- **Event-driven**: Signal handling and graceful shutdown
- **Resource Management**: Proper cleanup and connection management

## Important Implementation Details

### Wake Word to Conversation Handoff
- **Immediate Response**: Wake word detection stops monitoring
- **Quick Initialization**: Realtime API connection established
- **Seamless Transition**: Direct audio stream handoff
- **Acknowledgment**: Audio confirmation of wake word detection

### Real-time Audio Processing
- **Streaming Input**: Continuous audio capture during conversation
- **VAD Integration**: Smart silence detection and audio quality
- **Low Latency**: Direct audio streaming to/from OpenAI
- **Format Handling**: Proper audio format conversion and management

### Error Resilience and Logging
- **Comprehensive Logging**: All events logged to `logs/realtime_voice_assistant.log`
- **Error Recovery**: Graceful handling of API failures
- **Connection Management**: Automatic reconnection and cleanup
- **Resource Cleanup**: Proper disposal of audio resources and connections

### Performance Optimizations
- **Minimal Buffer Delays**: Real-time audio processing
- **Efficient Memory Usage**: Streaming instead of buffering large audio
- **Fast Wake Word Detection**: High sensitivity Porcupine settings
- **Async Everywhere**: Non-blocking operations throughout

## Development Guidelines

### Testing Real-time Components
When working with real-time audio:
1. Test on actual hardware (Raspberry Pi preferred)
2. Verify API access to OpenAI Realtime API
3. Test with various acoustic environments
4. Monitor latency and responsiveness
5. Validate conversation flow and timeout handling

### API Requirements
OpenAI Realtime API considerations:
- **GA Access**: Uses the generally available Realtime API (not beta)
- **Model**: `gpt-realtime` (configurable)
- **Rate Limits**: Monitor API usage and implement backoff if needed
- **Connection Management**: Handle WebSocket connections properly

### Asynchronous Programming
Maintain async/await throughout:
- All audio operations should be non-blocking
- Use proper asyncio patterns for concurrent operations
- Handle cancellation and cleanup properly
- Avoid blocking calls in async contexts

### Configuration and Environment
- API keys can be in config file or environment variables
- Validate all required keys and files at startup
- Provide clear error messages for missing requirements
- Support both development and production configurations

## Dependencies and Requirements

### Python Packages
- `openai>=1.3.0`: OpenAI API client
- `websockets>=12.0`: WebSocket connection to Realtime API
- `pvporcupine>=3.0.0`: Picovoice wake word detection
- `pyaudio>=0.2.11`: Audio input/output
- `numpy>=1.24.0`: Audio processing
- `soundfile>=0.12.1`: Audio file reading
- `python-dotenv>=1.0.0`: Environment variable management
- `ytmusicapi>=1.3.0`: YouTube Music search
- `yt-dlp>=2024.1.0`: YouTube audio download
- `pygame>=2.5.0`: Music playback
- `requests>=2.31.0`: HTTP requests
- `Pillow>=10.0.0`: Thumbnail image processing and terminal rendering

### System Requirements
- Python 3.8+
- PortAudio development libraries
- Working microphone and audio output
- Internet connection for API access
- OpenAI API key with Realtime API access

### Hardware Recommendations
- Raspberry Pi 4/5 or modern Linux/macOS system
- USB microphone or quality built-in mic
- Good speakers or headphones for clear audio
- Stable internet connection for real-time API calls

This architecture provides a modern, responsive voice assistant with natural conversation capabilities through OpenAI's cutting-edge Realtime API.