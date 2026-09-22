import asyncio
import base64
import json
import logging
import os
import time
from typing import Callable, Optional

import numpy as np
import pyaudio
import websockets

from music_commands import MusicCommandHandler


class RealtimeVoiceClient:
    """Handles real-time conversation using OpenAI Realtime API"""

    DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1"
    DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
    DEFAULT_REALTIME_VOICE = "marin"
    VALID_REALTIME_VOICES = {
        "alloy", "ash", "ballad", "coral", "echo",
        "sage", "shimmer", "verse", "marin", "cedar"
    }
    
    def __init__(self, config: dict, log_function: Optional[Callable] = None, music_handler: Optional['MusicCommandHandler'] = None):
        """
        Initialize realtime voice client
        
        Args:
            config: Configuration dictionary
            log_function: Optional logging function
            music_handler: Optional music command handler for pause/resume control
        """
        self.config = config
        self.log_function = log_function
        self.websocket = None
        self.is_connected = False
        self.audio = None
        self.stream = None
        self.conversation_should_end = False
        self.last_activity_time = None
        self.last_user_activity_time = None
        self.is_assistant_speaking = False
        self._assistant_finished_time = None
        self._assistant_text_buffer = ""
        self._consecutive_assistant_turns = 0
        self._max_consecutive_turns = 2
        self._noise_transcript_count = 0

        # Get API key
        self.api_key = config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required for realtime voice")
        
        # End conversation phrases
        self.end_phrases = [
            "goodbye", "bye", "see you later", "talk to you later", 
            "that's all", "thanks", "thank you", "stop", "end conversation",
            "quit", "exit", "done", "finished"
        ]
        
        # Configure logging
        self._setup_logging()
        
        # Initialize audio
        self._init_audio()
        
        # Use provided music handler or create new one
        self.music_handler = music_handler or MusicCommandHandler(log_function)
        
    def _setup_logging(self):
        """Setup logging for the realtime client"""
        self.logger = logging.getLogger(__name__)
        
    def _log(self, log_type: str, message: str):
        """Log message if logging function is available"""
        if self.log_function:
            try:
                self.log_function(log_type, message)
            except Exception as e:
                print(f"Error logging realtime event: {e}")
        else:
            self.logger.info(f"[{log_type}] {message}")
    
    def _init_audio(self):
        """Initialize PyAudio for microphone input and speaker output"""
        self.audio = pyaudio.PyAudio()

    def _get_realtime_model(self) -> str:
        """Return the configured Realtime model name."""
        return self.config.get("realtime_model", self.DEFAULT_REALTIME_MODEL)

    def _get_realtime_voice(self) -> str:
        """Return a valid Realtime voice, falling back to the recommended default."""
        voice = self.config.get("realtime_voice", self.DEFAULT_REALTIME_VOICE)
        if voice in self.VALID_REALTIME_VOICES:
            return voice

        self._log(
            "REALTIME_CONFIG",
            f"Unsupported realtime voice '{voice}', falling back to '{self.DEFAULT_REALTIME_VOICE}'"
        )
        return self.DEFAULT_REALTIME_VOICE

    def _build_transcription_config(self) -> dict:
        """Build optional realtime transcription settings."""
        transcription_config = {
            "model": self.config.get(
                "transcription_model",
                self.DEFAULT_TRANSCRIPTION_MODEL
            )
        }

        language = self.config.get("transcription_language")
        if language and language != "auto":
            transcription_config["language"] = language

        return transcription_config

    def _build_session_instructions(self) -> str:
        """Build a concise instruction block tuned for voice and tool use."""
        return (
            "You are a helpful voice assistant. "
            "You only speak English and Chinese (Mandarin). "
            "Reply in whichever of those languages the user is speaking. "
            "If audio is noisy or ambiguous, prefer English or Mandarin and ask for a brief repeat instead of guessing another language. "
            "You have music tools available and should use them whenever the user wants to play, pause, resume, stop, skip music, or check what's playing. "
            "Keep responses concise and complete. "
            "Do not end responses with follow-up questions. "
            "The user will say the wake word again if they need more help."
        )

    def _build_session_config(self) -> dict:
        """Build the GA Realtime session configuration."""
        model = self._get_realtime_model()

        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": model,
                "instructions": self._build_session_instructions(),
                "output_modalities": ["audio"],
                "tool_choice": "auto",
                "tools": [
                    {
                        "type": "function",
                        "name": "play_music",
                        "description": "Search for and play a song or artist from YouTube Music.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The song name, artist, or search query to play"
                                }
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "pause_music",
                        "description": "Pause the currently playing music.",
                        "parameters": {"type": "object", "properties": {}}
                    },
                    {
                        "type": "function",
                        "name": "resume_music",
                        "description": "Resume paused music.",
                        "parameters": {"type": "object", "properties": {}}
                    },
                    {
                        "type": "function",
                        "name": "stop_music",
                        "description": "Stop the currently playing music completely.",
                        "parameters": {"type": "object", "properties": {}}
                    },
                    {
                        "type": "function",
                        "name": "get_music_status",
                        "description": "Get the current music playback status (what's playing, paused, etc.).",
                        "parameters": {"type": "object", "properties": {}}
                    },
                    {
                        "type": "function",
                        "name": "skip_song",
                        "description": "Skip the current song.",
                        "parameters": {"type": "object", "properties": {}}
                    }
                ],
                "audio": {
                    "input": {
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000
                        },
                        "transcription": self._build_transcription_config(),
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500
                        }
                    },
                    "output": {
                        "format": {
                            "type": "audio/pcm",
                            "rate": 24000
                        },
                        "voice": self._get_realtime_voice()
                    }
                }
            }
        }
        
    async def initialize(self):
        """Initialize the realtime service connection"""
        try:
            # Connect to OpenAI Realtime API
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Get model from config or use default
            model = self._get_realtime_model()
            
            self.websocket = await websockets.connect(
                f"wss://api.openai.com/v1/realtime?model={model}",
                additional_headers=headers
            )
            
            session_config = self._build_session_config()
            
            await self.websocket.send(json.dumps(session_config))
            
            self._log("REALTIME_INIT", "Realtime voice client initialized successfully")
            
        except Exception as e:
            self._log("REALTIME_ERROR", f"Failed to initialize realtime client: {e}")
            raise
    
    async def start_conversation(self):
        """Start the realtime conversation"""
        if not self.websocket:
            await self.initialize()
        
        try:
            # Pause music if playing to avoid audio conflicts
            if self.music_handler:
                music_status = self.music_handler.get_status()
                if music_status.get('is_playing') and not music_status.get('is_paused'):
                    await self.music_handler.pause_for_conversation()
                    self._log("MUSIC_AUTO_PAUSE", "Automatically paused music for conversation")
            
            self.is_connected = True
            self.conversation_should_end = False
            self.last_activity_time = time.time()
            self.last_user_activity_time = time.time()
            self._consecutive_assistant_turns = 0
            self._noise_transcript_count = 0

            self._log("REALTIME_START", "Started realtime conversation")
            
            # Start audio input stream
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                input=True,
                frames_per_buffer=1024
            )
            
            # Start listening tasks
            listen_task = asyncio.create_task(self._listen_for_audio())
            response_task = asyncio.create_task(self._handle_responses())
            silence_task = asyncio.create_task(self._monitor_silence())
            
            # Wait for tasks to complete
            await asyncio.gather(listen_task, response_task, silence_task)
            
        except Exception as e:
            self._log("REALTIME_ERROR", f"Error starting conversation: {e}")
            raise
    
    async def _listen_for_audio(self):
        """Listen for audio input and send to realtime API.

        The mic stays active even while the assistant speaks, enabling
        barge-in (interruption). The OpenAI Realtime API's built-in VAD
        detects user speech during a response and truncates its output.
        """
        try:
            while self.is_connected and not self.conversation_should_end:
                if not self.stream:
                    await asyncio.sleep(0.01)
                    continue

                # Read audio data
                audio_data = self.stream.read(1024, exception_on_overflow=False)

                # Check for audio activity
                volume = self._calculate_rms(audio_data)

                if volume > 100:  # Threshold for detecting speech
                    self.last_activity_time = time.time()
                    self.last_user_activity_time = time.time()

                # Convert to base64 for transmission
                audio_b64 = base64.b64encode(audio_data).decode('utf-8')
                
                # Send audio to API
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64
                }
                
                await self.websocket.send(json.dumps(audio_event))
                
                # Small delay to prevent overwhelming the API
                await asyncio.sleep(0.01)
                
        except Exception as e:
            self._log("REALTIME_ERROR", f"Error in audio listening: {e}")

    @staticmethod
    def _calculate_rms(audio_data: bytes) -> float:
        """Calculate PCM16 RMS without overflowing the input data type."""
        samples = np.frombuffer(audio_data, dtype=np.int16)
        if samples.size == 0:
            return 0.0

        float_samples = samples.astype(np.float32)
        return float(np.sqrt(np.mean(np.square(float_samples))))
    
    async def _handle_responses(self):
        """Handle responses from the realtime API"""
        try:
            while self.is_connected and self.websocket and not self.conversation_should_end:
                # Receive message from API
                message = await self.websocket.recv()
                event = json.loads(message)
                
                event_type = event.get("type")
                
                if event_type == "conversation.item.input_audio_transcription.completed":
                    # Handle transcription of user input
                    transcript = event.get("transcript", "")
                    if transcript:
                        self._log("USER_TRANSCRIPT", transcript)

                        # Detect background noise (kids, TV, etc.)
                        if self._is_noise_transcript(transcript):
                            self._noise_transcript_count += 1
                            self._log("NOISE_DETECTED",
                                      f"Noise transcript #{self._noise_transcript_count}: '{transcript}'")
                            if self._noise_transcript_count >= 2:
                                self._log("CONVERSATION_END_DETECTED",
                                          f"Noisy environment: {self._noise_transcript_count} noise transcripts")
                                print("\n[Noisy environment detected, ending conversation...]")
                                self.conversation_should_end = True
                                await self.stop_conversation()
                                return
                            # Don't reset consecutive turn counter for noise
                        else:
                            # Real speech — reset noise and consecutive counters
                            self._noise_transcript_count = 0
                            self._consecutive_assistant_turns = 0

                            # Check if user wants to end conversation
                            if self._should_end_conversation(transcript):
                                print("\n[Ending conversation...]")
                                self.conversation_should_end = True
                                await self.stop_conversation()
                                return
                
                elif event_type == "response.output_audio.delta":
                    # Handle audio response
                    audio_data = event.get("delta")
                    if audio_data:
                        # Mark assistant as speaking to prevent input feedback
                        self.is_assistant_speaking = True

                        # Decode and play audio
                        audio_bytes = base64.b64decode(audio_data)
                        self._play_audio(audio_bytes)
                
                elif event_type == "response.output_audio_transcript.delta":
                    # Handle assistant transcript when output modality is audio
                    text = event.get("delta")
                    if text:
                        self.is_assistant_speaking = True
                        if not self._assistant_text_buffer:
                            print("Assistant: ", end="", flush=True)
                        self._assistant_text_buffer += text
                        print(text, end="", flush=True)

                elif event_type == "response.output_text.delta":
                    # Handle text-only response fallback
                    text = event.get("delta")
                    if text:
                        self.is_assistant_speaking = True
                        if not self._assistant_text_buffer:
                            print("Assistant: ", end="", flush=True)
                        self._assistant_text_buffer += text
                        print(text, end="", flush=True)

                elif event_type == "response.done":
                    response = event.get("response", {})
                    status = response.get("status")
                    status_details = response.get("status_details") or {}

                    if status == "failed":
                        error = status_details.get("error") or {}
                        message = error.get("message", "Realtime response failed.")
                        self._log("REALTIME_ERROR", f"Response failed: {error}")
                        print(f"\n[Realtime API error: {message}]")
                        self.conversation_should_end = True
                        await self.stop_conversation()
                        return

                    if status == "cancelled":
                        self._log("REALTIME_CANCELLED", f"Response cancelled: {status_details}")
                        print("\n[Realtime response cancelled]")
                        continue

                    print()  # New line after response
                    # Log the complete assistant response once
                    if self._assistant_text_buffer:
                        self._log("ASSISTANT_RESPONSE", self._assistant_text_buffer)
                        self._assistant_text_buffer = ""
                    self.is_assistant_speaking = False
                    self._assistant_finished_time = time.time()

                    # Track consecutive assistant turns without user input
                    self._consecutive_assistant_turns += 1
                    if self._consecutive_assistant_turns >= self._max_consecutive_turns:
                        self._log("CONVERSATION_END_DETECTED",
                                  f"Ending: {self._consecutive_assistant_turns} consecutive assistant turns without user input")
                        print(f"\n[No user input after {self._consecutive_assistant_turns} responses, ending conversation...]")
                        self.conversation_should_end = True
                        await self.stop_conversation()
                        return
                    
                elif event_type == "response.function_call_arguments.done":
                    # LLM decided to call a music function
                    call_id = event.get("call_id", "")
                    fn_name = event.get("name", "")
                    raw_args = event.get("arguments", "{}")
                    try:
                        fn_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        fn_args = {}

                    self._log("FUNCTION_CALL", f"{fn_name}({fn_args})")

                    # Execute via music handler
                    result = await self.music_handler.execute(fn_name, fn_args)
                    result_text = result.get("response", "Done.")
                    print(f"\n[Function {fn_name}: {result_text}]")

                    # Send function output back to the model
                    func_output = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(result)
                        }
                    }
                    await self.websocket.send(json.dumps(func_output))

                    # If play succeeded, end conversation and return to wake word mode
                    if result.get("action") == "play" and result.get("success"):
                        # Let the model acknowledge before ending
                        await self.websocket.send(json.dumps({"type": "response.create"}))
                        # Wait briefly for the acknowledgment audio to start
                        # The conversation will end after silence timeout or next response.done
                        print("[Music started - will return to wake word detection mode]")
                        self.conversation_should_end = True
                        await self.stop_conversation()
                        return
                    else:
                        # Trigger model to respond to the user with the result
                        await self.websocket.send(json.dumps({"type": "response.create"}))

                elif event_type == "input_audio_buffer.speech_started":
                    self.last_user_activity_time = time.time()
                    # Only reset consecutive turn counter if we haven't been
                    # seeing noise — otherwise let the limit kick in faster.
                    if self._noise_transcript_count == 0:
                        self._consecutive_assistant_turns = 0

                    # If assistant was mid-response, this is a barge-in
                    if self.is_assistant_speaking:
                        self.is_assistant_speaking = False
                        self._log("BARGE_IN", "User interrupted assistant response")

                elif event_type == "error":
                    error = event.get("error", {})
                    self._log("REALTIME_ERROR", f"API Error: {error}")
                
        except Exception as e:
            self._log("REALTIME_ERROR", f"Error handling responses: {e}")
    
    def _should_end_conversation(self, text: str) -> bool:
        """Check if the user wants to end the conversation"""
        text_lower = text.lower().strip()

        # Check for exact matches and partial matches
        for phrase in self.end_phrases:
            if phrase in text_lower:
                self._log("CONVERSATION_END_DETECTED", f"End phrase detected: '{phrase}' in '{text}'")
                return True

        return False

    def _is_noise_transcript(self, text: str) -> bool:
        """Check if transcript is background noise rather than intentional speech.

        In noisy environments (house with kids, TV, etc.) the mic picks up
        ambient sounds that get transcribed as short incoherent fragments.
        Detecting these lets us bail out quickly instead of trying to respond.
        """
        cleaned = ''.join(c for c in text.lower() if c.isalnum() or c.isspace()).strip()
        words = cleaned.split()

        if not words:
            return True

        # Single-word transcripts that are common noise artifacts
        single_word_noise = {
            "hmm", "mm", "uh", "um", "ah", "oh", "huh",
            "ha", "haha", "la", "da", "na", "ba", "bah",
            "the", "a", "and", "but", "or", "is", "it",
            "you", "i", "so", "to", "do", "if", "in",
        }
        if len(words) == 1 and words[0] in single_word_noise:
            return True

        # All words identical (e.g. "uh uh uh", "the the the")
        if len(words) >= 2 and len(set(words)) == 1:
            return True

        # Short transcript made entirely of common filler / function words
        filler_words = single_word_noise | {
            "yeah", "yep", "no", "okay", "ok", "hey", "like", "just",
            "what", "that", "this", "right", "we", "they", "he", "she",
            "me", "my", "can", "not", "on", "of", "at", "for",
            "up", "with", "are", "was", "be", "have", "has",
            "go", "get", "got", "let", "see", "come", "here", "there",
        }
        if len(words) <= 3 and all(w in filler_words for w in words):
            return True

        return False
    
    async def _monitor_silence(self):
        """Monitor for prolonged silence and end conversation.

        Tracks user activity (not assistant speech) to decide when a
        conversation is over. After the assistant finishes a response,
        a shorter timeout applies — if the user doesn't speak within
        that window, the conversation ends. The user can always start
        a new conversation by saying the wake word.
        """
        try:
            base_timeout = self.config.get("silence_timeout", 8)
            post_response_timeout = self.config.get("post_response_timeout", 6)

            while self.is_connected and not self.conversation_should_end:
                now = time.time()

                # Never time out while the assistant is still speaking
                if self.is_assistant_speaking:
                    await asyncio.sleep(1)
                    continue

                # After assistant finishes, measure silence from when it
                # finished (not from when the user last spoke), so a long
                # assistant answer doesn't cause an immediate timeout.
                if (self._assistant_finished_time
                        and self._assistant_finished_time > (self.last_user_activity_time or 0)):
                    ref_time = self._assistant_finished_time
                    effective_timeout = post_response_timeout
                else:
                    ref_time = self.last_user_activity_time or self.last_activity_time
                    effective_timeout = base_timeout

                if ref_time:
                    silence = now - ref_time
                    if silence > effective_timeout:
                        print(f"\n[No user activity for {effective_timeout:.0f}s, ending conversation...]")
                        self.conversation_should_end = True
                        await self.stop_conversation()
                        return

                await asyncio.sleep(1)

        except Exception as e:
            self._log("REALTIME_ERROR", f"Error monitoring silence: {e}")
    
    def _play_audio(self, audio_data: bytes):
        """Play audio data through speakers"""
        try:
            # Create output stream if needed
            if not hasattr(self, 'output_stream') or not self.output_stream:
                self.output_stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=24000,
                    output=True
                )
            
            # Play the audio
            self.output_stream.write(audio_data)
            
        except Exception as e:
            self._log("REALTIME_ERROR", f"Error playing audio: {e}")
    
    async def send_text(self, text: str):
        """Send text message to start conversation"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            # Create conversation item
            conversation_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": text
                        }
                    ]
                }
            }
            
            await self.websocket.send(json.dumps(conversation_item))
            
            # Trigger response
            response_create = {
                "type": "response.create"
            }
            
            await self.websocket.send(json.dumps(response_create))
            
            self._log("REALTIME_TEXT", f"Sent text: {text}")
            
        except Exception as e:
            self._log("REALTIME_ERROR", f"Error sending text: {e}")
    
    async def stop_conversation(self):
        """Stop the realtime conversation"""
        self.is_connected = False
        self.is_assistant_speaking = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if hasattr(self, 'output_stream') and self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        # Resume music if it was paused for conversation
        if self.music_handler:
            try:
                resumed = await self.music_handler.resume_after_conversation()
                if resumed:
                    self._log("MUSIC_AUTO_RESUME", "Automatically resumed music after conversation")
            except Exception as e:
                self._log("MUSIC_ERROR", f"Error resuming music after conversation: {e}")
        
        self._log("REALTIME_STOP", "Stopped realtime conversation")
    
    def cleanup(self):
        """Clean up resources"""
        try:
            # Stop conversation synchronously
            if self.is_connected:
                self.is_connected = False
                self.is_assistant_speaking = False

                # Close audio streams
                if self.stream:
                    try:
                        self.stream.stop_stream()
                        self.stream.close()
                        self.stream = None
                    except Exception as e:
                        self._log("REALTIME_ERROR", f"Error closing input stream: {e}")

                if hasattr(self, 'output_stream') and self.output_stream:
                    try:
                        self.output_stream.stop_stream()
                        self.output_stream.close()
                        self.output_stream = None
                    except Exception as e:
                        self._log("REALTIME_ERROR", f"Error closing output stream: {e}")
                
                # Close websocket connection
                if self.websocket:
                    try:
                        # Close websocket synchronously if possible
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Schedule close for later if loop is running
                            asyncio.create_task(self.websocket.close())
                        self.websocket = None
                    except Exception as e:
                        self._log("REALTIME_ERROR", f"Error closing websocket: {e}")
            
            # Cleanup music handler
            if hasattr(self, 'music_handler'):
                self.music_handler.cleanup()
            
            # Terminate PyAudio
            if self.audio:
                try:
                    self.audio.terminate()
                except Exception as e:
                    self._log("REALTIME_ERROR", f"Error terminating PyAudio: {e}")
                    
        except Exception as e:
            print(f"Error during realtime client cleanup: {e}")
