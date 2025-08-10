#!/usr/bin/env python3

import os
import sys
import json
import asyncio
import logging
import signal
import time
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import pyaudio
import soundfile as sf
import numpy as np

from wake_word_detector import WakeWordDetector
from realtime_voice_client import RealtimeVoiceClient
from music_commands import MusicCommandHandler


class RealtimeVoiceAssistant:
    """Main realtime voice assistant using wake word detection + OpenAI Realtime API"""
    
    def __init__(self, config_file: str = "../config/config.json"):
        """Initialize the realtime voice assistant"""
        # Load environment variables from .env file
        self._load_env_vars()
        
        self.config = self._load_config(config_file)
        self.running = False
        
        # Initialize logging
        self._setup_logging()
        
        # Initialize components
        print("Initializing realtime voice assistant...")
        
        # Music command handler (shared across components)
        self.music_handler = MusicCommandHandler(self._log_event)
        
        # Wake word detector
        self.wake_word_detector = WakeWordDetector(self.config, self._log_event)
        
        # Realtime voice client
        self.realtime_client = RealtimeVoiceClient(self.config, self._log_event, self.music_handler)
        
        print("Realtime voice assistant initialized successfully!")
    
    def _load_env_vars(self):
        """Load environment variables from .env file"""
        # Look for .env file in parent directory (project root)
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
            print(f"Loaded environment variables from: {env_path}")
        else:
            print("No .env file found - using system environment variables")
        
    def _load_config(self, config_file: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Config file not found: {config_file}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing config file: {e}")
            return {}
    
    def _setup_logging(self):
        """Setup logging for the assistant"""
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Setup logger
        self.logger = logging.getLogger('realtime_voice_assistant')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers.clear()
        
        # Create file handler
        log_file = os.path.join(log_dir, 'realtime_voice_assistant.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Add handler
        self.logger.addHandler(file_handler)
        
        print(f"Logging setup complete. Log file: {log_file}")
    
    def _log_event(self, event_type: str, message: str):
        """Log events from components"""
        try:
            self.logger.info(f"{event_type}: {message}")
        except Exception as e:
            print(f"Error logging event: {e}")
    
    async def play_wake_word_acknowledgment(self):
        """Play acknowledgment after wake word detection using static audio file"""
        print("Wake word detected! Playing acknowledgment...")
        try:
            # Play the static audio file
            audio_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'audio', 'hi_there.wav')
            
            # Check if audio file exists
            if not os.path.exists(audio_file_path):
                print(f"Audio file not found: {audio_file_path}")
                self._log_event("WAKE_WORD_ACK_ERROR", f"Audio file not found: {audio_file_path}")
                return
            
            # Load audio file
            audio_data, sample_rate = sf.read(audio_file_path)
            
            # Create PyAudio instance
            p = pyaudio.PyAudio()
            
            # Determine channels
            channels = 1 if len(audio_data.shape) == 1 else audio_data.shape[1]
            
            # Open stream with proper settings
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=int(sample_rate),
                output=True,
                frames_per_buffer=1024
            )
            
            # Convert to float32 if needed
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # Ensure audio is in the right range for float32 (-1.0 to 1.0)
            if np.max(np.abs(audio_data)) > 1.0:
                audio_data = audio_data / np.max(np.abs(audio_data))
            
            # Play audio in chunks to avoid buffer issues
            chunk_size = 1024
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                stream.write(chunk.tobytes())
            
            # Cleanup
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # Add delay after audio playback
            await asyncio.sleep(0.3)
            
            print("Starting conversation...")
            
        except Exception as e:
            print(f"Error playing wake word acknowledgment: {e}")
            import traceback
            traceback.print_exc()
            self._log_event("WAKE_WORD_ACK_ERROR", f"Failed to play acknowledgment: {e}")
    
    async def play_bye_bye_sound(self):
        """Play ByeBye sound after conversation ends (skip if music is playing)"""
        # Check if music is currently playing
        try:
            music_status = self.music_handler.get_status()
            if music_status.get('is_playing', False):
                print("Music is playing, skipping ByeBye sound...")
                self._log_event("BYE_BYE_SKIP", "Skipped ByeBye sound due to active music playback")
                return
        except Exception as e:
            print(f"Error checking music status: {e}")
            # Continue with ByeBye sound if we can't check music status
        
        print("Playing ByeBye sound...")
        try:
            # Play the static audio file
            audio_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'audio', 'bye_bye.wav')
            
            # Check if audio file exists
            if not os.path.exists(audio_file_path):
                print(f"Audio file not found: {audio_file_path}")
                self._log_event("BYE_BYE_ERROR", f"Audio file not found: {audio_file_path}")
                return
            
            # Load audio file
            audio_data, sample_rate = sf.read(audio_file_path)
            
            # Create PyAudio instance
            p = pyaudio.PyAudio()
            
            # Determine channels
            channels = 1 if len(audio_data.shape) == 1 else audio_data.shape[1]
            
            # Open stream with proper settings
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=int(sample_rate),
                output=True,
                frames_per_buffer=1024
            )
            
            # Convert to float32 if needed
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # Ensure audio is in the right range for float32 (-1.0 to 1.0)
            if np.max(np.abs(audio_data)) > 1.0:
                audio_data = audio_data / np.max(np.abs(audio_data))
            
            # Play audio in chunks to avoid buffer issues
            chunk_size = 1024
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                stream.write(chunk.tobytes())
            
            # Cleanup
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # Add delay after audio playback
            await asyncio.sleep(0.3)
            
        except Exception as e:
            print(f"Error playing ByeBye sound: {e}")
            import traceback
            traceback.print_exc()
            self._log_event("BYE_BYE_ERROR", f"Failed to play ByeBye sound: {e}")
        
        # Initialize realtime client if needed
        if not self.realtime_client.is_connected:
            await self.realtime_client.initialize()
    
    async def handle_wake_word_detection(self):
        """Handle wake word detection and start realtime conversation"""
        try:
            # Play acknowledgment
            await self.play_wake_word_acknowledgment()
            
            # Start realtime conversation
            await self.realtime_client.start_conversation()
            
            # Send initial greeting to start the conversation
            await self.realtime_client.send_text("Hello! I heard you call me. How can I help you?")
            
            self._log_event("CONVERSATION_START", "Started realtime conversation after wake word")
            
        except Exception as e:
            print(f"Error handling wake word detection: {e}")
            self._log_event("CONVERSATION_ERROR", f"Failed to start conversation: {e}")
    
    async def run_continuous_mode(self):
        """Run in continuous listening mode"""
        print("\n=== Realtime Voice Assistant Started ===")
        print(f"Wake word: {self.wake_word_detector.wake_keywords[0]}")
        print("Say the wake word to start a conversation.")
        print("The assistant will use OpenAI's Realtime API for natural conversation.")
        print("Press Ctrl+C to exit.\n")
        
        self.running = True
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            print("\nShutdown signal received...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            while self.running:
                # Listen for wake word
                detected_keyword = await self.wake_word_detector.listen_for_wake_word()
                
                if detected_keyword and self.running:
                    print(f"Wake word '{detected_keyword}' detected!")
                    
                    # Handle wake word detection
                    await self.handle_wake_word_detection()
                    
                    # Wait for conversation to complete or timeout
                    conversation_timeout = self.config.get("conversation_timeout", 30)
                    try:
                        await asyncio.wait_for(
                            self._wait_for_conversation_end(),
                            timeout=conversation_timeout
                        )
                    except asyncio.TimeoutError:
                        print("Conversation timed out, returning to wake word detection")
                        await self.realtime_client.stop_conversation()
                    
                    # Play ByeBye sound after conversation ends
                    await self.play_bye_bye_sound()
                    
                    print("\nReady for next wake word...")
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)
                
        except KeyboardInterrupt:
            print("\nKeyboard interrupt detected")
        except Exception as e:
            print(f"Error in continuous mode: {e}")
            self._log_event("SYSTEM_ERROR", f"Continuous mode error: {e}")
        finally:
            await self.cleanup()
    
    async def _wait_for_conversation_end(self):
        """Wait for conversation to end"""
        # Wait for the realtime client to indicate conversation should end
        while (self.realtime_client.is_connected and 
               not self.realtime_client.conversation_should_end and 
               self.running):
            await asyncio.sleep(0.1)
    
    async def cleanup(self):
        """Clean up resources"""
        print("\nCleaning up...")
        
        # Stop realtime client
        if hasattr(self, 'realtime_client'):
            await self.realtime_client.stop_conversation()
            self.realtime_client.cleanup()
        
        # Stop wake word detector
        if hasattr(self, 'wake_word_detector'):
            await self.wake_word_detector.stop_listening()
            self.wake_word_detector.cleanup()
        
        # Cleanup music handler
        if hasattr(self, 'music_handler'):
            self.music_handler.cleanup()
        
        print("Realtime voice assistant stopped.")


async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Realtime Smart Voice Assistant")
    parser.add_argument("--config", default="../config/config.json",
                       help="Configuration file path")
    
    args = parser.parse_args()
    
    try:
        assistant = RealtimeVoiceAssistant(config_file=args.config)
        await assistant.run_continuous_mode()
        
    except Exception as e:
        print(f"Error starting realtime voice assistant: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())