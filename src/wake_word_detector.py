import os
import platform
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pvporcupine
import pyaudio

PORCUPINE_MODEL_VERSION = "4_0_0"
WAKE_WORD = "Hi Taco"


def _platform_suffix() -> str:
    """Return the Picovoice filename suffix for the current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_arm = "arm" in machine or "aarch64" in machine

    if system == "darwin":
        return "mac_apple" if is_arm else "mac"
    if system == "linux":
        return "raspberry-pi" if is_arm else "linux-x86_64"
    if system == "windows":
        return "windows-amd64"

    raise RuntimeError(f"Unsupported wake-word platform: {system} ({machine})")


def _compatible_keyword_path(access_key: str) -> Path:
    """Return a Porcupine 4 keyword file, training it on first use if needed."""
    project_root = Path(__file__).resolve().parent.parent
    platform_suffix = _platform_suffix()
    keyword_path = project_root / (
        f"Hi-Taco_en_{platform_suffix}_v{PORCUPINE_MODEL_VERSION}.ppn"
    )

    if keyword_path.exists():
        return keyword_path

    temporary_path = keyword_path.with_name(
        f".{keyword_path.stem}.tmp{keyword_path.suffix}"
    )
    print(
        f"No Porcupine 4 Hi Taco model found for {platform_suffix}; "
        "generating one now..."
    )

    try:
        temporary_path.unlink(missing_ok=True)
        pvporcupine.train_wake_word_from_phrase(
            access_key=access_key,
            output_path=str(temporary_path),
            language="en",
            phrase=WAKE_WORD,
        )
        temporary_path.replace(keyword_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Could not generate a Porcupine 4 Hi Taco model. Update "
            "PORCUPINE_ACCESS_KEY with an active key from "
            "https://console.picovoice.ai/ and rerun ./run.sh, or download a "
            f"Porcupine 4 model to {keyword_path}."
        ) from None

    print(f"Generated Porcupine 4 keyword file: {keyword_path.name}")
    return keyword_path


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
            custom_ppn_path = _compatible_keyword_path(access_key)
            print(f"✓ Using Hi Taco keyword file: {custom_ppn_path.name}")

            keyword_paths = [str(custom_ppn_path)]
            self.wake_keywords = [WAKE_WORD]
            
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
            raise RuntimeError(f"Porcupine initialization failed: {e}") from e
    
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
            # Synchronous cleanup - stop listening directly
            self.is_listening = False
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                except Exception as e:
                    print(f"Error closing stream during cleanup: {e}")

        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                print(f"Error terminating audio during cleanup: {e}")

        if self.porcupine:
            try:
                self.porcupine.delete()
            except Exception as e:
                print(f"Error deleting porcupine during cleanup: {e}")

        print("Wake word detector cleaned up.")
