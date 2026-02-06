import asyncio
import json
import os
import logging
import pyaudio
import numpy as np
import websockets
import base64
import time
from typing import Optional, Callable

from music_commands import MusicCommandHandler


class RealtimeVoiceClient:
    """Handles real-time conversation using OpenAI Realtime API"""
    
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
        self.is_assistant_speaking = False
        self._assistant_finished_time = None
        self._assistant_text_buffer = ""

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
        logging.basicConfig(level=logging.INFO)
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
        
    async def initialize(self):
        """Initialize the realtime service connection"""
        try:
            # Connect to OpenAI Realtime API
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Get model from config or use default
            model = self.config.get("realtime_model", "gpt-realtime")
            
            self.websocket = await websockets.connect(
                f"wss://api.openai.com/v1/realtime?model={model}",
                additional_headers=headers
            )
            
            # Send session configuration (GA API format)
            session_config = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": "You are a helpful voice assistant with full music capabilities. I have a built-in music player that can play songs from YouTube Music. When users ask about music, tell them about available music features like 'play [song name]', 'pause', 'resume', 'stop music', 'next song', etc. Never say you cannot play music - I can play any song they request. The music system handles all music commands automatically, so just acknowledge their requests and be encouraging about the music features.",
                    "audio": {
                        "input": {
                            "format": {
                                "type": "audio/pcm",
                                "rate": 24000
                            },
                            "transcription": {
                                "model": "whisper-1"
                            },
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
                            "voice": "alloy"
                        }
                    }
                }
            }
            
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
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                volume = np.sqrt(np.mean(audio_array**2))

                if volume > 100:  # Threshold for detecting speech
                    self.last_activity_time = time.time()

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
                        
                        # Check for music commands and handle directly
                        if await self.music_handler.is_music_command(transcript):
                            print(f"\n[Music command detected: {transcript}]")
                            
                            # Handle music command directly
                            music_response = await self.music_handler.handle_command(transcript)
                            print(f"[Music Response: {music_response.get('response', 'Done.')}]")
                            
                            # If music started playing, end conversation and return to wake word detection
                            if music_response.get('action') == 'play' and music_response.get('success'):
                                print("[Music started - returning to wake word detection mode]")
                                self.conversation_should_end = True
                                await self.stop_conversation()
                                return

                            continue
                        
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

                        # Update activity time when assistant speaks
                        self.last_activity_time = time.time()
                        
                        # Decode and play audio
                        audio_bytes = base64.b64decode(audio_data)
                        self._play_audio(audio_bytes)
                
                elif event_type == "response.output_text.delta":
                    # Handle text response — accumulate for logging
                    text = event.get("delta")
                    if text:
                        self.is_assistant_speaking = True
                        self._assistant_text_buffer += text
                        print(f"Assistant: {text}", end="", flush=True)

                elif event_type == "response.done":
                    print()  # New line after response
                    # Log the complete assistant response once
                    if self._assistant_text_buffer:
                        self._log("ASSISTANT_RESPONSE", self._assistant_text_buffer)
                        self._assistant_text_buffer = ""
                    self.is_assistant_speaking = False
                    self._assistant_finished_time = time.time()
                    
                elif event_type == "input_audio_buffer.speech_started":
                    # User started speaking — if assistant was mid-response,
                    # this is a barge-in / interruption.
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
    
    async def _monitor_silence(self):
        """Monitor for prolonged silence and end conversation.

        Uses a shorter timeout when waiting for the user to respond after
        the assistant finishes speaking, and a longer timeout while the
        user is mid-turn (to allow thinking pauses).
        """
        try:
            base_timeout = self.config.get("silence_timeout", 10)  # 10 seconds default
            post_response_grace = 3  # extra seconds after assistant finishes

            while self.is_connected and not self.conversation_should_end:
                if self.last_activity_time:
                    silence_duration = time.time() - self.last_activity_time

                    # Give extra grace period right after assistant finishes
                    # so the user has time to formulate a response
                    effective_timeout = base_timeout
                    if hasattr(self, '_assistant_finished_time') and self._assistant_finished_time:
                        time_since_response = time.time() - self._assistant_finished_time
                        if time_since_response < post_response_grace:
                            effective_timeout = base_timeout + post_response_grace

                    if silence_duration > effective_timeout:
                        print(f"\n[No activity for {effective_timeout:.0f} seconds, ending conversation...]")
                        self.conversation_should_end = True
                        await self.stop_conversation()
                        return

                await asyncio.sleep(1)  # Check every second
                
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
    
    async def _send_music_response(self, response_text: str):
        """Send music response as assistant message"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            # Create assistant response item
            conversation_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": response_text
                        }
                    ]
                }
            }
            
            await self.websocket.send(json.dumps(conversation_item))
            
            # Trigger TTS response
            response_create = {
                "type": "response.create"
            }
            
            await self.websocket.send(json.dumps(response_create))
            
            self._log("MUSIC_RESPONSE", f"Sent music response: {response_text}")
            
        except Exception as e:
            self._log("REALTIME_ERROR", f"Error sending music response: {e}")
    
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