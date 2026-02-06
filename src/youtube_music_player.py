#!/usr/bin/env python3

import asyncio
import subprocess
import threading
import time
import os
import tempfile
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Callable
import pygame
from ytmusicapi import YTMusic
import yt_dlp


class YouTubeMusicPlayer:
    """YouTube Music player for voice assistant"""
    
    def __init__(self, log_function: Optional[Callable] = None):
        """
        Initialize YouTube Music player
        
        Args:
            log_function: Optional logging function
        """
        self.log_function = log_function
        self.ytmusic = None
        self.current_song = None
        self.is_playing = False
        self.is_paused = False
        self.was_paused_for_conversation = False  # Track if music was paused for conversation
        self.playback_thread = None
        
        # Setup music cache directory
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'music_cache')
        self.metadata_file = os.path.join(self.cache_dir, 'metadata.json')
        self._ensure_cache_directory()
        
        # Initialize pygame mixer
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.init()
        
        # Initialize YouTube Music API (no auth required for search)
        try:
            self.ytmusic = YTMusic()
            self._log("MUSIC_INIT", "YouTube Music player initialized successfully")
        except Exception as e:
            self._log("MUSIC_ERROR", f"Failed to initialize YouTube Music API: {e}")
            raise
    
    def _log(self, log_type: str, message: str):
        """Log message if logging function is available"""
        if self.log_function:
            try:
                self.log_function(log_type, message)
            except Exception as e:
                print(f"Error logging music event: {e}")
        else:
            print(f"[{log_type}] {message}")
    
    def _ensure_cache_directory(self):
        """Ensure cache directory exists"""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            self._log("CACHE_INIT", f"Cache directory ready: {self.cache_dir}")
        except Exception as e:
            self._log("CACHE_ERROR", f"Failed to create cache directory: {e}")
    
    def _generate_song_id(self, video_id: str, title: str, artist: str) -> str:
        """Generate unique identifier for a song"""
        # Create unique ID based on video_id, title, and artist
        song_data = f"{video_id}_{title}_{artist}".lower()
        return hashlib.md5(song_data.encode()).hexdigest()[:12]
    
    def _get_cached_file_path(self, song_id: str) -> str:
        """Get the file path for a cached song"""
        return os.path.join(self.cache_dir, f"{song_id}.mp3")
    
    def _load_metadata(self) -> Dict:
        """Load metadata from cache"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self._log("CACHE_ERROR", f"Error loading metadata: {e}")
        return {}
    
    def _save_metadata(self, metadata: Dict):
        """Save metadata to cache"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log("CACHE_ERROR", f"Error saving metadata: {e}")
    
    def _is_song_cached(self, song_id: str) -> bool:
        """Check if song is already cached"""
        cached_file = self._get_cached_file_path(song_id)
        metadata = self._load_metadata()
        
        # Check if file exists and is in metadata
        return (os.path.exists(cached_file) and 
                song_id in metadata and 
                os.path.getsize(cached_file) > 0)
    
    def _cache_song(self, song_id: str, video_id: str, title: str, artist: str):
        """Add song to cache metadata"""
        metadata = self._load_metadata()
        current_time = datetime.now()
        
        metadata[song_id] = {
            'video_id': video_id,
            'title': title,
            'artist': artist,
            'cached_at': current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'cached_timestamp': time.time(),  # Keep numeric timestamp for sorting/calculations
            'play_count': metadata.get(song_id, {}).get('play_count', 0) + 1,
            'last_played': current_time.strftime('%Y-%m-%d %H:%M:%S')
        }
        self._save_metadata(metadata)
    
    async def search_songs(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search for songs on YouTube Music
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of song dictionaries
        """
        try:
            self._log("MUSIC_SEARCH", f"Searching for: {query}")
            
            # Search for songs
            search_results = self.ytmusic.search(query, filter='songs', limit=limit)
            
            songs = []
            for result in search_results:
                song = {
                    'videoId': result.get('videoId'),
                    'title': result.get('title', 'Unknown Title'),
                    'artist': ', '.join([artist['name'] for artist in result.get('artists', [])]) or 'Unknown Artist',
                    'duration': result.get('duration', 'Unknown'),
                    'thumbnail': result.get('thumbnails', [{}])[0].get('url') if result.get('thumbnails') else None
                }
                songs.append(song)
            
            self._log("MUSIC_SEARCH_RESULT", f"Found {len(songs)} songs for '{query}'")
            return songs
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error searching songs: {e}")
            return []
    
    async def play_song(self, video_id: str, title: str = "Unknown", artist: str = "Unknown") -> bool:
        """
        Play a song by video ID (with caching support)
        
        Args:
            video_id: YouTube video ID
            title: Song title for logging
            artist: Artist name for caching
            
        Returns:
            True if playback started successfully
        """
        try:
            # Stop current playback if any
            await self.stop()
            
            # Generate unique song ID
            song_id = self._generate_song_id(video_id, title, artist)
            cached_file = self._get_cached_file_path(song_id)
            
            self._log("MUSIC_PLAY", f"Starting playback: {title} by {artist}")
            
            # Check if song is cached
            if self._is_song_cached(song_id):
                self._log("CACHE_HIT", f"Playing cached version: {title}")
                audio_file = cached_file
                # Update play count
                self._cache_song(song_id, video_id, title, artist)
            else:
                self._log("CACHE_MISS", f"Downloading: {title}")
                
                # Download audio stream URL
                audio_url = await self._get_audio_stream_url(video_id)
                if not audio_url:
                    self._log("MUSIC_ERROR", f"Failed to get audio stream for: {title}")
                    return False
                
                # Download to cache
                if not await self._download_to_cache(audio_url, cached_file, song_id, video_id, title, artist):
                    self._log("MUSIC_ERROR", f"Failed to download: {title}")
                    return False
                
                audio_file = cached_file
            
            # Start playback in separate thread
            self.current_song = {
                'videoId': video_id,
                'title': title,
                'artist': artist,
                'song_id': song_id,
                'audio_file': audio_file
            }
            
            self.is_playing = True
            self.is_paused = False
            
            # Start playback thread
            self.playback_thread = threading.Thread(
                target=self._play_cached_audio,
                args=(audio_file, f"{artist} - {title}"),
                daemon=True
            )
            self.playback_thread.start()
            
            return True
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error playing song: {e}")
            return False
    
    async def _get_audio_stream_url(self, video_id: str) -> Optional[str]:
        """Get audio stream URL using yt-dlp"""
        try:
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'outtmpl': '-',  # Don't save to file
            }
            
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info without downloading
                info = ydl.extract_info(youtube_url, download=False)
                
                # Get the best audio format
                formats = info.get('formats', [])
                audio_formats = [f for f in formats if f.get('acodec') != 'none']
                
                if audio_formats:
                    # Sort by audio quality (bitrate)
                    audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                    best_audio = audio_formats[0]
                    return best_audio.get('url')
            
            return None
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error getting audio stream URL: {e}")
            return None
    
    async def _download_to_cache(self, audio_url: str, cached_file: str, song_id: str, video_id: str, title: str, artist: str) -> bool:
        """Download audio to cache file"""
        try:
            # Download audio to cache file using async subprocess
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', audio_url, '-acodec', 'mp3', '-ab', '192k',
                cached_file, '-y',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self._log("CACHE_ERROR", f"FFmpeg error downloading {title}: {stderr.decode()}")
                # Clean up failed download
                if os.path.exists(cached_file):
                    try:
                        os.unlink(cached_file)
                    except Exception:
                        pass
                return False

            # Add to cache metadata
            self._cache_song(song_id, video_id, title, artist)

            self._log("CACHE_DOWNLOAD", f"Cached: {title} ({song_id})")
            return True

        except Exception as e:
            self._log("CACHE_ERROR", f"Error downloading to cache: {e}")
            # Clean up failed download
            if os.path.exists(cached_file):
                try:
                    os.unlink(cached_file)
                except Exception as cleanup_error:
                    self._log("CACHE_ERROR", f"Error cleaning up failed download: {cleanup_error}")
            return False
    
    def _play_cached_audio(self, audio_file: str, title: str):
        """Play cached audio file using pygame (runs in separate thread)"""
        try:
            if not os.path.exists(audio_file):
                self._log("MUSIC_ERROR", f"Cached file not found: {audio_file}")
                return
            
            self._log("MUSIC_PLAYBACK", f"Playing cached audio: {title}")
            
            # Load and play with pygame
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            
            # Monitor playback
            while pygame.mixer.music.get_busy() and self.is_playing:
                if self.is_paused:
                    pygame.mixer.music.pause()
                    while self.is_paused and self.is_playing:
                        time.sleep(0.1)
                    if self.is_playing:
                        pygame.mixer.music.unpause()
                
                time.sleep(0.1)
            
            if self.is_playing:
                self._log("MUSIC_FINISHED", f"Finished playing: {title}")
                self.is_playing = False
                self.current_song = None
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error in cached audio playback: {e}")
        finally:
            self.is_playing = False
    
    
    async def pause(self) -> bool:
        """Pause current playback"""
        if self.is_playing and not self.is_paused:
            self.is_paused = True
            self._log("MUSIC_PAUSE", f"Paused: {self.current_song.get('title', 'Unknown') if self.current_song else 'Unknown'}")
            return True
        return False
    
    async def resume(self) -> bool:
        """Resume paused playback"""
        if self.is_playing and self.is_paused:
            self.is_paused = False
            self.was_paused_for_conversation = False  # Clear conversation pause flag
            self._log("MUSIC_RESUME", f"Resumed: {self.current_song.get('title', 'Unknown') if self.current_song else 'Unknown'}")
            return True
        return False
    
    async def pause_for_conversation(self) -> bool:
        """Pause music for voice conversation"""
        if self.is_playing and not self.is_paused:
            self.is_paused = True
            self.was_paused_for_conversation = True
            self._log("MUSIC_CONV_PAUSE", f"Paused for conversation: {self.current_song.get('title', 'Unknown') if self.current_song else 'Unknown'}")
            return True
        return False
    
    async def resume_after_conversation(self) -> bool:
        """Resume music after voice conversation if it was paused for conversation"""
        if self.is_playing and self.is_paused and self.was_paused_for_conversation:
            self.is_paused = False
            self.was_paused_for_conversation = False
            self._log("MUSIC_CONV_RESUME", f"Resumed after conversation: {self.current_song.get('title', 'Unknown') if self.current_song else 'Unknown'}")
            return True
        return False
    
    async def stop(self) -> bool:
        """Stop current playback"""
        if self.is_playing:
            self.is_playing = False
            self.is_paused = False
            
            # Stop pygame mixer if initialized
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except pygame.error as e:
                self._log("MUSIC_ERROR", f"Pygame mixer stop error: {e}")
            
            # Wait for playback thread to finish
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_thread.join(timeout=2)
            
            song_title = self.current_song.get('title', 'Unknown') if self.current_song else 'Unknown'
            self.current_song = None
            
            self._log("MUSIC_STOP", f"Stopped: {song_title}")
            
            return True
        return False
    
    def get_cache_info(self) -> Dict:
        """Get information about cached songs"""
        try:
            metadata = self._load_metadata()
            total_songs = len(metadata)
            
            # Calculate total cache size
            total_size = 0
            for song_id in metadata:
                cached_file = self._get_cached_file_path(song_id)
                if os.path.exists(cached_file):
                    total_size += os.path.getsize(cached_file)
            
            return {
                'total_songs': total_songs,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'cache_dir': self.cache_dir,
                'most_played': sorted(metadata.items(), 
                                    key=lambda x: x[1].get('play_count', 0), 
                                    reverse=True)[:5]
            }
        except Exception as e:
            self._log("CACHE_ERROR", f"Error getting cache info: {e}")
            return {'error': str(e)}
    
    def get_status(self) -> Dict:
        """Get current playback status"""
        return {
            'is_playing': self.is_playing,
            'is_paused': self.is_paused,
            'current_song': self.current_song
        }
    
    async def play_search_result(self, query: str, index: int = 0) -> bool:
        """
        Search and play the first (or specified index) result
        
        Args:
            query: Search query
            index: Index of search result to play (default: 0)
            
        Returns:
            True if song started playing
        """
        try:
            # Search for songs
            songs = await self.search_songs(query, limit=max(5, index + 1))
            
            if not songs:
                self._log("MUSIC_ERROR", f"No songs found for: {query}")
                return False
            
            if index >= len(songs):
                self._log("MUSIC_ERROR", f"Search result index {index} out of range (found {len(songs)} songs)")
                return False
            
            # Play the selected song
            song = songs[index]
            return await self.play_song(song['videoId'], song['title'], song['artist'])
            
        except Exception as e:
            self._log("MUSIC_ERROR", f"Error playing search result: {e}")
            return False
    
    def cleanup(self):
        """Clean up resources"""
        try:
            # Stop any current playback synchronously
            if self.is_playing:
                self.is_playing = False
                self.is_paused = False
                
                # Stop pygame mixer if initialized
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except pygame.error as e:
                    self._log("MUSIC_ERROR", f"Pygame mixer stop error: {e}")
                
                # Wait for playback thread to finish
                if self.playback_thread and self.playback_thread.is_alive():
                    self.playback_thread.join(timeout=2)
                
                self.current_song = None
            
            # Cleanup pygame if initialized
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.quit()
            except pygame.error as e:
                self._log("MUSIC_ERROR", f"Pygame mixer cleanup error: {e}")

            self._log("MUSIC_CLEANUP", "YouTube Music player cleaned up")

        except Exception as e:
            self._log("MUSIC_ERROR", f"Error during cleanup: {e}")