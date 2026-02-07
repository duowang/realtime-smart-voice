#!/usr/bin/env python3

import asyncio
from typing import Optional, Dict, Callable
from youtube_music_player import YouTubeMusicPlayer


class MusicCommandHandler:
    """Handles music-related voice commands via LLM function calling"""

    def __init__(self, log_function: Optional[Callable] = None):
        self.log_function = log_function
        self.music_player = YouTubeMusicPlayer(log_function)
    
    def _log(self, log_type: str, message: str):
        """Log message if logging function is available"""
        if self.log_function:
            try:
                self.log_function(log_type, message)
            except Exception as e:
                print(f"Error logging music command: {e}")
        else:
            print(f"[{log_type}] {message}")
    
    async def execute(self, function_name: str, arguments: dict) -> Dict:
        """
        Execute a music function by name.

        Args:
            function_name: One of play_music, pause_music, resume_music,
                           stop_music, get_music_status, skip_song
            arguments: Dict of arguments (e.g. {"query": "..."} for play_music)

        Returns:
            Dictionary with response information
        """
        self._log("MUSIC_FUNCTION_CALL", f"{function_name}({arguments})")

        handlers = {
            "play_music": lambda: self._handle_play_command(arguments.get("query", "")),
            "pause_music": lambda: self._handle_pause_command(),
            "resume_music": lambda: self._handle_resume_command(),
            "stop_music": lambda: self._handle_stop_command(),
            "get_music_status": lambda: self._handle_status_command(),
            "skip_song": lambda: self._handle_next_command(),
        }

        handler = handlers.get(function_name)
        if not handler:
            return {
                "success": False,
                "response": f"Unknown music function: {function_name}",
                "action": "unknown",
            }

        try:
            return await handler()
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error executing {function_name}: {e}")
            return {
                "success": False,
                "response": f"Error executing {function_name}: {e}",
                "action": "error",
            }
    
    async def _handle_play_command(self, query: str) -> Dict:
        """Handle play music command"""
        try:
            self._log("MUSIC_PLAY_CMD", f"Playing: {query}")
            
            # Search and play the first result
            success = await self.music_player.play_search_result(query)
            
            if success:
                return {
                    'success': True,
                    'response': f"Now playing {query} from YouTube Music.",
                    'action': 'play',
                    'query': query
                }
            else:
                return {
                    'success': False,
                    'response': f"Sorry, I couldn't find or play '{query}' on YouTube Music. Please try a different song.",
                    'action': 'play_failed',
                    'query': query
                }
                
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in play command: {e}")
            return {
                'success': False,
                'response': f"Sorry, I had trouble playing '{query}'. Please try again.",
                'action': 'play_error',
                'query': query
            }
    
    async def _handle_pause_command(self) -> Dict:
        """Handle pause music command"""
        try:
            status = self.music_player.get_status()
            
            if not status['is_playing']:
                return {
                    'success': False,
                    'response': "There's no music currently playing to pause.",
                    'action': 'pause_no_music'
                }
            
            if status['is_paused']:
                return {
                    'success': False,
                    'response': "The music is already paused.",
                    'action': 'pause_already_paused'
                }
            
            success = await self.music_player.pause()
            
            if success:
                song_title = status['current_song'].get('title', 'Unknown') if status['current_song'] else 'the music'
                return {
                    'success': True,
                    'response': f"Paused {song_title}.",
                    'action': 'pause'
                }
            else:
                return {
                    'success': False,
                    'response': "Sorry, I couldn't pause the music.",
                    'action': 'pause_failed'
                }
                
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in pause command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble pausing the music.",
                'action': 'pause_error'
            }
    
    async def _handle_resume_command(self) -> Dict:
        """Handle resume music command"""
        try:
            status = self.music_player.get_status()
            
            if not status['is_playing']:
                return {
                    'success': False,
                    'response': "There's no music to resume. Try asking me to play a song.",
                    'action': 'resume_no_music'
                }
            
            if not status['is_paused']:
                return {
                    'success': False,
                    'response': "The music is already playing.",
                    'action': 'resume_not_paused'
                }
            
            success = await self.music_player.resume()
            
            if success:
                song_title = status['current_song'].get('title', 'Unknown') if status['current_song'] else 'the music'
                return {
                    'success': True,
                    'response': f"Resumed {song_title}.",
                    'action': 'resume'
                }
            else:
                return {
                    'success': False,
                    'response': "Sorry, I couldn't resume the music.",
                    'action': 'resume_failed'
                }
                
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in resume command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble resuming the music.",
                'action': 'resume_error'
            }
    
    async def _handle_stop_command(self) -> Dict:
        """Handle stop music command"""
        try:
            status = self.music_player.get_status()
            
            if not status['is_playing']:
                return {
                    'success': False,
                    'response': "There's no music currently playing to stop.",
                    'action': 'stop_no_music'
                }
            
            song_title = status['current_song'].get('title', 'Unknown') if status['current_song'] else 'the music'
            success = await self.music_player.stop()
            
            if success:
                return {
                    'success': True,
                    'response': f"Stopped {song_title}.",
                    'action': 'stop'
                }
            else:
                return {
                    'success': False,
                    'response': "Sorry, I couldn't stop the music.",
                    'action': 'stop_failed'
                }
                
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in stop command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble stopping the music.",
                'action': 'stop_error'
            }
    
    async def _handle_status_command(self) -> Dict:
        """Handle music status command"""
        try:
            status = self.music_player.get_status()
            
            if not status['is_playing']:
                return {
                    'success': True,
                    'response': "No music is currently playing.",
                    'action': 'status',
                    'status': 'not_playing'
                }
            
            current_song = status['current_song']
            if current_song:
                song_info = current_song.get('title', 'Unknown Song')
                
                if status['is_paused']:
                    response = f"Currently paused: {song_info}"
                    playback_status = 'paused'
                else:
                    response = f"Currently playing: {song_info}"
                    playback_status = 'playing'
                
                return {
                    'success': True,
                    'response': response,
                    'action': 'status',
                    'status': playback_status,
                    'song': song_info
                }
            else:
                return {
                    'success': True,
                    'response': "Music is playing but I can't identify the current song.",
                    'action': 'status',
                    'status': 'playing_unknown'
                }
                
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in status command: {e}")
            return {
                'success': False,
                'response': "Sorry, I couldn't get the music status.",
                'action': 'status_error'
            }
    
    async def _handle_next_command(self) -> Dict:
        """Handle next/skip command"""
        try:
            # For now, just stop current song (next song functionality would need playlist support)
            status = self.music_player.get_status()
            
            if not status['is_playing']:
                return {
                    'success': False,
                    'response': "No music is currently playing to skip.",
                    'action': 'next_no_music'
                }
            
            # Stop current song (placeholder for next functionality)
            await self.music_player.stop()
            
            return {
                'success': True,
                'response': "Skipped. Ask me to play another song.",
                'action': 'next'
            }
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in next command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble skipping the song.",
                'action': 'next_error'
            }
    
    async def pause_for_conversation(self) -> bool:
        """Pause music for conversation"""
        try:
            return await self.music_player.pause_for_conversation()
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error pausing for conversation: {e}")
            return False
    
    async def resume_after_conversation(self) -> bool:
        """Resume music after conversation"""
        try:
            return await self.music_player.resume_after_conversation()
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error resuming after conversation: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Get current music status"""
        return self.music_player.get_status()
    
    def cleanup(self):
        """Clean up resources"""
        try:
            self.music_player.cleanup()
            self._log("MUSIC_COMMANDS_CLEANUP", "Music command handler cleaned up")
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error during cleanup: {e}")