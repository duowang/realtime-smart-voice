# Realtime Smart Voice Assistant

**🎯 Direct Voice-to-Voice AI Conversations with OpenAI Realtime API**
**🍓 Optimized for Raspberry Pi - Bring AI Voice to Edge Devices**

A cutting-edge voice assistant powered by OpenAI's Realtime API that enables **direct audio-to-audio conversations** with AI for low-latency interactions. **Designed to run efficiently on Raspberry Pi** for edge AI deployments.

## ✨ Key Features

- **🎤 Direct Voice Processing**: OpenAI Realtime API streams input/output audio in real time
- **⚡ Ultra-Low Latency**: Streaming audio eliminates traditional STT→LLM→TTS delays  
- **🍓 Raspberry Pi Ready**: Optimized for Pi 4/5 with efficient resource usage and ARM64 support
- **🎯 Wake Word Detection**: Uses Picovoice Porcupine with platform-specific `.ppn` files
- **🎵 YouTube Music Integration**: Voice-controlled music playback with intelligent caching
- **💾 Smart Music Cache**: Local caching reduces playback latency for frequently played songs
- **🔄 Continuous Conversations**: Natural back-and-forth without re-triggering wake word
- **⚡ Asynchronous Architecture**: Non-blocking audio processing optimized for Pi hardware

## Requirements

**🍓 Raspberry Pi (Recommended):**
- Raspberry Pi 4 or 5 (2GB+ RAM recommended)
- Raspberry Pi OS (64-bit)
- USB microphone or HAT with microphone
- Speakers, headphones, or audio HAT

**💻 Alternative Platforms:**
- Linux/macOS with Python 3.8+
- Apple Silicon Mac (ARM64) / Intel Mac supported

**🔑 API Keys:**
- OpenAI API key with Realtime API access
- Picovoice access key (free tier available)
- Custom wake word file (.ppn) for your platform

## Installation

1. **Clone and navigate to the project:**
   ```bash
   git clone https://github.com/duowang/realtime-smart-voice.git
   cd realtime-smart-voice
   ```

2. **Install system dependencies:**

   **🍓 On Raspberry Pi:**
   ```bash
   sudo apt update
   sudo apt install -y portaudio19-dev python3-pyaudio python3-pip python3-venv ffmpeg
   
   # Optional: Test your microphone
   sudo apt install -y alsa-utils
   arecord -l  # List audio devices
   ```
   
   **🐧 On Ubuntu/Debian:**
   ```bash
   sudo apt update  
   sudo apt install -y portaudio19-dev python3-pyaudio python3-pip python3-venv ffmpeg
   ```
   
   **🍎 On macOS:**
   ```bash
   brew install portaudio ffmpeg
   ```

3. **Get Picovoice Access Key and wake word file:**

   **🔑 Step 1: Get Picovoice Access Key**
   1. Go to [Picovoice Console](https://console.picovoice.ai/)
   2. Sign up for a free account
   3. Navigate to "Access Keys" in the dashboard
   4. Copy your access key (starts with a long alphanumeric string)
   
   **🎤 Step 2: Create/Download Wake Word**
   1. In Picovoice Console, go to "Porcupine" → "Wake Word Engine"
   2. Click "Train Custom Wake Word"
   3. **Enter your desired phrase**:
      - **Default**: `Hi Taco` (recommended for this project)
      - **Custom**: Any phrase you want (e.g., "Hey Assistant", "Computer", "Jarvis")
      - **Tips**: 2-3 syllables work best, avoid common words
   4. Select your target platform:
      - **Raspberry Pi**: Choose "Raspberry Pi" 
      - **Mac**: Choose "macOS" (specify Intel or Apple Silicon)
      - **Linux**: Choose "Linux (x86_64)"
   5. Train the wake word (takes a few minutes)
   6. Download the `.ppn` file when training completes
   7. **Place the `.ppn` file in your project root directory**
   8. Name the file using the platform format expected by this project (see Wake Word Setup below)

4. **Set up API keys:**
   
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env file and add your API keys
   nano .env
   ```
   
   Your `.env` file should look like:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   PORCUPINE_ACCESS_KEY=your_porcupine_access_key_here
   ```

5. **Run the assistant:**
   ```bash
   ./run.sh
   ```

## Usage

1. **Start the assistant:**
   ```bash
   ./run.sh
   ```

2. **Activate with wake word:**
   - Say your wake word (default: "Hi Taco") to start a conversation  
   - The assistant will acknowledge and begin listening
   - Speak naturally - the conversation is real-time
   - Wake word file is loaded by platform-specific filename (see Wake Word Setup)

3. **🎵 Control music playback:**
   - **Play music**: "Play [song/artist name]", "Put on some music", "Start playing [song]"
   - **Control playback**: "Pause", "Resume", "Stop music"
   - **Music automatically pauses** during conversations and resumes after

4. **End conversations:**
   - **Voice commands**: Say "goodbye", "bye", "thanks", "stop", "done", etc.
   - **Silence timeout**: 15 seconds of no activity (configurable)
   - **Manual**: Press `Ctrl+C` to stop the entire assistant

5. **Exit:**
   - Press `Ctrl+C` to stop the assistant completely

## Configuration

### Environment Variables (.env file)
The recommended way to configure API keys:
```bash
OPENAI_API_KEY=your_openai_api_key_here
PORCUPINE_ACCESS_KEY=your_porcupine_access_key_here
```

### Configuration File (config/config.json)
Additional settings:
```json
{
  "openai_api_key": null,
  "realtime_model": "gpt-realtime",
  "chatgpt_model": "gpt-4o",
  "conversation_timeout": 30,
  "silence_timeout": 15,
  "porcupine_access_key": "optional-if-using-env"
}
```

**Priority order:** Environment variables (.env) → System environment → config.json

## 🎯 Wake Word Setup

### Default Setup
The project defaults to the "Hi Taco" wake word and looks for platform-specific `.ppn` filenames.

### Using Your Own Wake Word File
1. **Train your wake word** in [Picovoice Console](https://console.picovoice.ai/)
2. **Download the `.ppn` file** for your platform  
3. **Place it in the project root** directory
4. Name it to match one of the expected patterns below (or update code paths if using a different name)

### Wake Word File Naming
The system automatically detects `.ppn` files based on platform:

**Expected filename patterns:**
```
Hi-Taco_en_raspberry-pi_v3_0_0.ppn   # Raspberry Pi
Hi-Taco_en_mac_v3_0_0.ppn            # macOS Intel
Hi-Taco_en_mac_apple_v3_0_0.ppn      # macOS Apple Silicon
Hi-Taco_en_linux-x86_64_v3_0_0.ppn   # Linux x86_64
```

### Best Practices
- **2-3 syllables** work best (e.g., "Hey Taco", "Computer", "Jarvis")
- **Avoid common words** that might trigger accidentally
- **Test in your environment** - some phrases work better in noisy conditions
- **Unique phrases** reduce false positives
- **Consider your accent** when training

Note: the current code path is hardcoded to look for `Hi-Taco...` filenames. If you use a different phrase filename, rename it to match the expected pattern or update `src/wake_word_detector.py`.

## 🎵 Music Features

### YouTube Music Integration
This assistant includes advanced music playback capabilities:

- **🎤 Voice-Controlled**: Control music entirely through voice commands
- **🔍 Intelligent Search**: Searches YouTube Music for songs, artists, albums
- **💾 Smart Caching**: Downloads and caches songs locally for faster playback
- **🎧 Background Playback**: Music continues in background while assistant listens for wake word
- **⏸️ Auto-Pause/Resume**: Music automatically pauses during conversations

### Music Commands
**🎵 Play Music:**
```
"Play [song name]"
"Play some music by [artist]"
"Put on [album name]"
"Start playing [song title]"
```

**⏯️ Control Playback:**
```
"Pause" / "Pause music"
"Resume" / "Continue playing"  
"Stop" / "Stop music"
"Hold on" (pause for conversation)
```

**🔄 Navigation and Volume (Current Status):**
```
"Next song" / "Skip"            # currently skips by stopping current song
"Previous song" / "Go back"     # not implemented yet
"Volume up" / "Volume down"     # not implemented yet
```

### Music Cache System
- **📁 Location**: `music_cache/` directory (automatically created)
- **🚀 Performance**: Cached songs start instantly without download delays
- **💾 Storage**: Uses efficient audio compression for Raspberry Pi storage
- **🧹 Auto-Management**: Metadata tracking for cache organization
- **🔒 Privacy**: All music cached locally - no cloud storage

## Project Structure

```
realtime-smart-voice/
├── src/
│   ├── realtime_voice_assistant.py    # Main application
│   ├── wake_word_detector.py          # Picovoice wake word detection
│   ├── realtime_voice_client.py       # OpenAI Realtime API websocket client
│   ├── music_commands.py              # Voice music command processing
│   └── youtube_music_player.py        # YouTube Music integration & caching
├── config/
│   └── config.json                    # Configuration file
├── music_cache/                      # Local music cache (auto-created)
│   └── metadata.json                 # Music cache metadata
├── logs/                              # Application logs
├── .env.example                       # Environment variables template
├── .env                              # Your API keys (create from .env.example)
├── .gitignore                        # Git ignore file
├── Hi-Taco_en_raspberry-pi_v3_0_0.ppn # Wake word file (Raspberry Pi)
├── Hi-Taco_en_mac_v3_0_0.ppn         # Wake word file (macOS Intel)
├── Hi-Taco_en_mac_apple_v3_0_0.ppn   # Wake word file (macOS Apple Silicon)
├── [YourWord]_en_[platform]_v3_0_0.ppn # Your custom wake word files
├── requirements.txt                   # Python dependencies
├── run.sh                            # Startup script
└── README.md
```

## Architecture

### Wake Word Detection
- **Picovoice Porcupine**: Offline, real-time wake word detection
- **Platform-Specific**: Optimized `.ppn` files for each platform (Pi, Mac, Linux)  
- **Asynchronous Processing**: Non-blocking audio monitoring

### Direct Audio-to-Audio Processing
- **OpenAI Realtime API**: Streaming input/output audio over a persistent websocket
- **Server VAD**: Built-in turn detection via `server_vad`
- **Transcription for routing**: Uses `whisper-1` transcription events to detect music/end commands
- **True real-time**: Continuous audio streaming with barge-in handling

### Data Flow
1. **Wake Word Detection**: Continuous monitoring for "Hi Taco" wake word
2. **Direct Audio Connection**: Realtime API connection established via websocket
3. **Audio-to-Audio Streaming**: Raw PCM audio sent directly to OpenAI Realtime
4. **Real-time AI Processing**: OpenAI returns streaming audio responses
5. **Command Routing**: User transcription events are used for music control and conversation end detection
6. **Continuous Loop**: Natural conversation flow until timeout or explicit end

## 🚀 Why This Matters - Revolutionary Voice Processing

**Traditional Voice Assistants:**
```
Voice Input → Speech-to-Text → LLM → Text-to-Speech → Voice Output
     ↓              ↓           ↓            ↓              ↓
   Latency      Processing   Latency    Processing      Latency
```

**This Project with OpenAI Realtime API:**
```
Voice Input ────────────→ Direct AI Processing ────────────→ Voice Output
     ↓                           ↓                              ↓
  Real-time           Server-side routing help            Real-time
```

### Technical Advantages:
- **🎯 Direct Audio Streaming**: Real-time PCM streaming minimizes latency
- **🍓 Edge AI Optimization**: Efficient resource usage perfect for Raspberry Pi deployment
- **🔄 Natural Conversation Flow**: Interruption handling and real-time back-and-forth
- **📊 Streaming Architecture**: Lightweight websocket client with async tasks
- **⚡ Asynchronous Design**: Non-blocking audio processing maximizes Pi hardware efficiency
- **🌐 Offline Wake Words**: Local processing reduces bandwidth and improves privacy

## Troubleshooting

### Audio Issues

**🍓 Raspberry Pi Audio Setup:**
```bash
# Test microphone
arecord -d 5 test.wav && aplay test.wav

# List audio devices
arecord -l && aplay -l

# Set default audio device (if needed)
sudo nano /usr/share/alsa/alsa.conf

# Check audio devices from Python
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)}') for i in range(p.get_device_count())]"
```

**Common Raspberry Pi Audio Issues:**
- **No microphone detected**: Check USB connection or enable I2S in raspi-config
- **Audio not working**: Try `sudo usermod -a -G audio $USER` then reboot
- **Permission denied**: Run `sudo chmod 666 /dev/snd/*` (temporary fix)

### Picovoice Setup Issues

**🔑 Access Key Problems:**
```bash
# Test your access key with a built-in wake word
python -c "
import pvporcupine
import os
from dotenv import load_dotenv
load_dotenv()
porcupine = pvporcupine.create(
    access_key=os.getenv('PORCUPINE_ACCESS_KEY'),
    keywords=['computer']
)
print('✅ Access key is valid!')
porcupine.delete()
"
```

**🎤 Wake Word File Issues:**
- **File not found**: Ensure your `.ppn` file is in the project root directory
- **Wrong platform**: Download the correct `.ppn` file for your platform:
  - Raspberry Pi: `Hi-Taco_en_raspberry-pi_v3_0_0.ppn`
  - macOS (Intel): `Hi-Taco_en_mac_v3_0_0.ppn`
  - macOS (Apple Silicon): `Hi-Taco_en_mac_apple_v3_0_0.ppn`
  - Linux: `Hi-Taco_en_linux-x86_64_v3_0_0.ppn`
- **Error code 00000136**: Usually indicates access key or platform compatibility issues

**🎯 Custom Wake Word Not Working:**
- **File naming**: Ensure the `.ppn` filename matches what the code expects
- **Test with default**: Try the included "Hi Taco" file first to verify setup
- **Custom phrase**: rename your custom `.ppn` to the expected `Hi-Taco_en_<platform>_v3_0_0.ppn` filename or update `src/wake_word_detector.py`
- **Retrain if needed**: Some phrases work better than others in your environment

**Free Tier Limits:**
- Picovoice free tier allows up to 3 custom wake words
- If you hit the limit, delete unused wake words in the console

### Music Playback Issues

**🎵 No Music Playing:**
```bash
# Check if pygame/audio dependencies are installed
python -c "import pygame; pygame.mixer.init(); print('✅ Audio system works!')"

# Test music cache directory
ls -la music_cache/
```

**🔍 Song Not Found:**
- Try being more specific: "Play [song title] by [artist]"
- Use popular song names that exist on YouTube Music
- Check your internet connection for YouTube Music search

**📦 Cache Issues:**
```bash
# Clear music cache if corrupted
rm -rf music_cache/
# Cache will be recreated automatically

# Check cache size (helpful for Raspberry Pi storage)
du -sh music_cache/
```

**🍓 Raspberry Pi Audio Issues:**
```bash
# Ensure audio is routed to headphones/speakers (not HDMI)
sudo raspi-config  # Advanced Options > Audio > Force 3.5mm jack

# Test pygame audio specifically
python -c "
import pygame
pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
pygame.mixer.init()
print('✅ Pygame audio initialized successfully!')
"
```

### API Issues
- Ensure OpenAI API key has access to the Realtime API
- Verify Picovoice access key is valid and not expired  
- Check internet connection for API calls

### Dependencies
```bash
# Reinstall requirements if needed
rm -rf venv
./run.sh
```

## Logging

All interactions are logged to `logs/realtime_voice_assistant.log`:
- Wake word detections
- Conversation starts/stops
- API interactions
- Error conditions
- Performance metrics

## License

MIT License - see [LICENSE](LICENSE) file for details.

**Note**: This project uses third-party services (OpenAI Realtime API, Picovoice) that have their own terms of service. Ensure compliance with their respective terms.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

See [Repository Guidelines](AGENTS.md) for detailed contributor expectations and workflows.
