import os
import struct
import platform
import pvporcupine
import pyaudio
import asyncio
from typing import Optional, List, Callable
import numpy as np


class WakeWordDetector:
    """Handles wake word detection using Porcupine for realtime voice assistant"""
    
    def __init__(self, config: dict, log_function: Optional[Callable] = None):
        """
        Initialize wake word detector
        
        Args:
            config: Configuration dictionary
            log_function: Optional logging function that takes (log_type: str, message: str)
        """
        self.config = config
        self.log_function = log_function
        self.porcupine = None
        self.wake_keywords = []
        self.audio = None
        self.stream = None
        self.is_listening = False
        
        # Initialize Porcupine
        self._init_porcupine()
        
        # Initialize PyAudio
        self._init_audio()
        
    def _init_porcupine(self):
        """Initialize Porcupine wake word detection"""
        access_key = self.config.get("porcupine_access_key") or os.getenv("PORCUPINE_ACCESS_KEY")
        
        if not access_key:
            error_msg = (
                "ERROR: Porcupine access key is required for wake word detection.\n"
                "Please get a free access key from: https://console.picovoice.ai/\n"
                "Add it to config.json as 'porcupine_access_key' or set PORCUPINE_ACCESS_KEY environment variable."
            )
            print(error_msg)
            raise RuntimeError("Porcupine access key is required. Cannot start wake word detector.")
        
        try:
            # Determine platform-specific .ppn file
            system = platform.system().lower()
            machine = platform.machine().lower()
            
            # Map platform to expected .ppn file suffix
            platform_suffix = ""
            if system == "darwin":  # macOS
                # Use generic mac file for both x86 and ARM64
                platform_suffix = "mac"
            elif system == "linux":
                if "arm" in machine or "aarch64" in machine:
                    platform_suffix = "raspberry-pi"
                else:
                    platform_suffix = "linux-x86_64"
            elif system == "windows":
                platform_suffix = "windows-amd64"
            else:
                # Fallback to raspberry-pi format (original)
                platform_suffix = "raspberry-pi"
            
            # Try platform-specific file first, then fallback to raspberry-pi
            ppn_filenames = [
                f"Hi-Taco_en_{platform_suffix}_v3_0_0.ppn",
                "Hi-Taco_en_raspberry-pi_v3_0_0.ppn"  # fallback
            ]
            
            custom_ppn_path = None
            for filename in ppn_filenames:
                potential_path = os.path.join(os.path.dirname(__file__), f"../{filename}")
                if os.path.exists(potential_path):
                    custom_ppn_path = potential_path
                    print(f"✓ Using Hi Taco keyword file: {filename}")
                    break
            
            if not custom_ppn_path:
                available_files = [f for f in os.listdir(os.path.dirname(__file__) + "/../") if f.startswith("Hi-Taco") and f.endswith(".ppn")]
                error_msg = (
                    f"Hi Taco .ppn file not found for platform: {system} ({machine})\n"
                    f"Tried: {ppn_filenames}\n"
                    f"Available .ppn files: {available_files}\n"
                    f"Please download the correct .ppn file for {platform_suffix} platform."
                )
                raise RuntimeError(error_msg)
            
            keyword_paths = [custom_ppn_path]
            self.wake_keywords = ["Hi Taco"]
            
            # Initialize Porcupine with moderate sensitivity to reduce false positives during music playback
            # Sensitivity: 0.0 (least sensitive) to 1.0 (most sensitive). 0.6 balances accuracy vs false positives
            self.porcupine = pvporcupine.create(
                access_key=access_key,
                keyword_paths=keyword_paths,
                sensitivities=[0.6] * len(keyword_paths)
            )
            
            print(f"Porcupine initialized with keywords: {self.wake_keywords}")
            print(f"Sample rate: {self.porcupine.sample_rate}, frame length: {self.porcupine.frame_length}")
            
        except Exception as e:
            print(f"Error initializing Porcupine: {e}")
            raise RuntimeError(f"Porcupine initialization failed: {e}")
    
    def _init_audio(self):
        """Initialize PyAudio for microphone input"""
        self.audio = pyaudio.PyAudio()
        
    def _log(self, log_type: str, message: str):
        """Log message if logging function is available"""
        if self.log_function:
            try:
                self.log_function(log_type, message)
            except Exception as e:
                print(f"Error logging wake word event: {e}")
        else:
            print(f"[{log_type}] {message}")
    
    async def start_listening(self):
        """Start continuous listening for wake words"""
        if self.is_listening:
            return
            
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.porcupine.sample_rate,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )
            
            self.is_listening = True
            print(f"Started listening for wake word: {self.wake_keywords[0]}")
            self._log("WAKE_WORD_START", "Started continuous wake word detection")
            
        except Exception as e:
            print(f"Error starting wake word detection: {e}")
            raise
    
    async def stop_listening(self):
        """Stop listening for wake words"""
        if not self.is_listening:
            return
            
        self.is_listening = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        self._log("WAKE_WORD_STOP", "Stopped wake word detection")
        print("Stopped wake word detection")
    
    async def listen_for_wake_word(self) -> Optional[str]:
        """
        Listen for wake word using Porcupine detection
        
        Returns:
            str: Detected wake word, or None if no wake word detected
        """
        if not self.is_listening:
            await self.start_listening()
        
        try:
            # Read audio frame
            audio_frame = self.stream.read(self.porcupine.frame_length, exception_on_overflow=False)
            
            # Convert to numpy array
            pcm = np.frombuffer(audio_frame, dtype=np.int16)
            
            # Process with Porcupine
            keyword_index = self.porcupine.process(pcm)
            
            if keyword_index >= 0:
                detected_keyword = self.wake_keywords[keyword_index]
                print(f"Wake word '{detected_keyword}' detected!")
                self._log("WAKE_WORD_DETECTED", f"Porcupine detected: '{detected_keyword}'")
                
                # Stop listening after detection
                await self.stop_listening()
                
                return detected_keyword
            
            return None
            
        except Exception as e:
            error_msg = f"Porcupine detection failed: {e}"
            print(f"Error in wake word detection: {e}")
            self._log("WAKE_WORD_ERROR", error_msg)
            return None
    
    def get_sample_rate(self) -> int:
        """Get the sample rate used by Porcupine"""
        return self.porcupine.sample_rate if self.porcupine else 16000
    
    def cleanup(self):
        """Clean up resources"""
        if self.is_listening:
            asyncio.create_task(self.stop_listening())
        
        if self.audio:
            self.audio.terminate()
        
        if self.porcupine:
            self.porcupine.delete()
        
        print("Wake word detector cleaned up.")