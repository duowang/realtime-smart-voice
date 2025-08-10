#!/usr/bin/env python3

import re
import asyncio
import subprocess
import platform
from typing import Optional, Dict, List, Callable
from youtube_music_player import YouTubeMusicPlayer


class MusicCommandHandler:
    """Handles music-related voice commands"""
    
    def __init__(self, log_function: Optional[Callable] = None):
        """
        Initialize music command handler
        
        Args:
            log_function: Optional logging function
        """
        self.log_function = log_function
        self.music_player = YouTubeMusicPlayer(log_function)
        
        # Music command patterns (English + Chinese)
        self.command_patterns = {
            'play': [
                # English
                r'play\s+(.+)',
                r'start playing\s+(.+)',
                r'put on\s+(.+)',
                r'listen to\s+(.+)',
                r'stream\s+(.+)',
                r'i want to hear\s+(.+)',
                r'can you play\s+(.+)',
                r'play some\s+(.+)',
                # Chinese
                r'播放\s*(.+)',
                r'放\s*(.+)',
                r'听\s*(.+)',
                r'我想听\s*(.+)',
                r'给我放\s*(.+)',
                r'来一首\s*(.+)',
                r'放首\s*(.+)'
            ],
            'pause': [
                # English
                r'pause\s*(music|song|track)?',
                r'stop playing',
                r'hold on',
                r'wait',
                r'freeze',
                r'halt',
                # Chinese
                r'暂停',
                r'停一下',
                r'等等',
                r'先停',
                r'暂停音乐',
                r'停止播放'
            ],
            'resume': [
                # English
                r'resume\s*(music|song|track)?',
                r'continue\s*(playing|music|song|track)?',
                r'unpause',
                r'keep playing',
                r'go on',
                r'carry on',
                r'keep going',
                # Chinese
                r'继续',
                r'继续播放',
                r'恢复',
                r'接着播',
                r'继续放',
                r'恢复播放'
            ],
            'stop': [
                # English
                r'stop\s*(music|song|track|playing)?',
                r'turn off\s*(music|song|track)?',
                r'end\s*(music|song|track)?',
                r'quit music',
                r'close music',
                r'shut off',
                # Chinese
                r'停止',
                r'关闭音乐',
                r'不听了',
                r'停止播放',
                r'关掉',
                r'别放了',
                r'结束播放'
            ],
            'status': [
                # English
                r'what.*playing',
                r'current song',
                r'music status',
                r'what.*music',
                r'what.*song',
                r'playing now',
                r'now playing',
                # Chinese
                r'现在播放.*',
                r'正在播放.*',
                r'在放什么',
                r'什么歌',
                r'现在什么歌',
                r'播放状态',
                r'音乐状态'
            ],
            'next': [
                # English
                r'next\s*(song|track)?',
                r'skip\s*(song|track)?',
                r'next one',
                r'skip this',
                r'change song',
                # Chinese
                r'下一首',
                r'跳过',
                r'换一首',
                r'切歌',
                r'下一个'
            ],
            'previous': [
                # English
                r'previous\s*(song|track)?',
                r'last\s*(song|track)?',
                r'back',
                r'go back',
                # Chinese
                r'上一首',
                r'前一首',
                r'返回',
                r'回到上一首'
            ],
            'volume_up': [
                # English
                r'volume up',
                r'louder',
                r'turn up',
                r'increase volume',
                # Chinese
                r'声音大一点',
                r'大声点',
                r'调高音量',
                r'音量增加'
            ],
            'volume_down': [
                # English
                r'volume down',
                r'quieter',
                r'turn down',
                r'decrease volume',
                r'lower volume',
                # Chinese
                r'声音小一点',
                r'小声点',
                r'调低音量',
                r'音量减少'
            ]
        }
    
    def _log(self, log_type: str, message: str):
        """Log message if logging function is available"""
        if self.log_function:
            try:
                self.log_function(log_type, message)
            except Exception as e:
                print(f"Error logging music command: {e}")
        else:
            print(f"[{log_type}] {message}")
    
    async def   is_music_command(self, text: str) -> bool:
        """
        Check if the text contains a music command
        
        Args:
            text: Input text to check
            
        Returns:
            True if text contains a music command
        """
        text_lower = text.lower().strip()
        
        self._log("MUSIC_COMMAND_CHECK", f"Checking text: '{text}' -> '{text_lower}'")
        
        # Check all command patterns
        for command_type, patterns in self.command_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    self._log("MUSIC_COMMAND_MATCH", f"Matched pattern '{pattern}' for command type '{command_type}'")
                    return True
        
        self._log("MUSIC_COMMAND_NO_MATCH", "No music command patterns matched")
        return False
    
    async def handle_command(self, text: str) -> Dict:
        """
        Handle music command and return response
        
        Args:
            text: Voice command text
            
        Returns:
            Dictionary with response information
        """
        text_lower = text.lower().strip()
        self._log("MUSIC_COMMAND", f"Processing command: {text}")
        
        try:
            # Play command
            for pattern in self.command_patterns['play']:
                match = re.search(pattern, text_lower)
                if match:
                    query = match.group(1).strip() if match.group(1) else text_lower.strip()
                    
                    # For patterns like "song by artist" or "artist - song", use the full text
                    if 'by' in text_lower or '-' in text_lower:
                        query = text_lower.strip()
                    
                    # Skip very short queries that might be false positives
                    if len(query) < 3:
                        continue
                        
                    return await self._handle_play_command(query)
            
            # Pause command
            for pattern in self.command_patterns['pause']:
                if re.search(pattern, text_lower):
                    return await self._handle_pause_command()
            
            # Resume command
            for pattern in self.command_patterns['resume']:
                if re.search(pattern, text_lower):
                    return await self._handle_resume_command()
            
            # Stop command
            for pattern in self.command_patterns['stop']:
                if re.search(pattern, text_lower):
                    return await self._handle_stop_command()
            
            # Status command
            for pattern in self.command_patterns['status']:
                if re.search(pattern, text_lower):
                    return await self._handle_status_command()
            
            # Next command
            for pattern in self.command_patterns['next']:
                if re.search(pattern, text_lower):
                    return await self._handle_next_command()
            
            # Previous command
            for pattern in self.command_patterns['previous']:
                if re.search(pattern, text_lower):
                    return await self._handle_previous_command()
            
            # Volume up command
            for pattern in self.command_patterns['volume_up']:
                if re.search(pattern, text_lower):
                    return await self._handle_volume_up_command()
            
            # Volume down command
            for pattern in self.command_patterns['volume_down']:
                if re.search(pattern, text_lower):
                    return await self._handle_volume_down_command()
            
            # Unknown music command
            return {
                'success': False,
                'response': "I didn't understand that music command. Try 'play [song]', 'pause', 'resume', 'stop', 'next', or 'previous'.",
                'action': 'unknown'
            }
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error handling music command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble with that music command. Please try again.",
                'action': 'error'
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
    
    async def _handle_previous_command(self) -> Dict:
        """Handle previous command"""
        try:
            return {
                'success': False,
                'response': "Previous song feature is not yet implemented. Try playing a specific song instead.",
                'action': 'previous_not_implemented'
            }
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in previous command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble with the previous command.",
                'action': 'previous_error'
            }
    
    async def _handle_volume_up_command(self) -> Dict:
        """Handle volume up command"""
        try:
            # Volume control would need to be implemented in the music player
            return {
                'success': False,
                'response': "Volume control is not yet implemented. Use your system volume controls.",
                'action': 'volume_not_implemented'
            }
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in volume up command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble with volume control.",
                'action': 'volume_error'
            }
    
    async def _handle_volume_down_command(self) -> Dict:
        """Handle volume down command"""
        try:
            # Volume control would need to be implemented in the music player
            return {
                'success': False,
                'response': "Volume control is not yet implemented. Use your system volume controls.",
                'action': 'volume_not_implemented'
            }
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in volume down command: {e}")
            return {
                'success': False,
                'response': "Sorry, I had trouble with volume control.",
                'action': 'volume_error'
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