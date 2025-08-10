#!/usr/bin/env python3

import os
import sys
import json
from openai import OpenAI

def generate_hi_there_audio():
    """Generate high-quality 'Hi There!' audio using OpenAI TTS API"""
    
    # Load environment variables manually
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Load API key from config or environment
    api_key = None
    try:
        with open("config/config.json", "r") as f:
            config = json.load(f)
            api_key = config.get("openai_api_key")
    except:
        pass
    
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("Error: OpenAI API key not found in config.json or OPENAI_API_KEY environment variable")
        return None
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    print("Generating 'Hi There!' audio using OpenAI TTS...")
    
    try:
        # Generate speech using OpenAI TTS with improved settings
        response = client.audio.speech.create(
            model="tts-1-hd",  # High-definition model for better quality
            voice="shimmer",   # More natural, warm, and human-like voice
            input="Hi there!",  # More natural capitalization
            response_format="wav",  # WAV format for better compatibility
            speed=1.0  # Normal speed for natural delivery
        )
        
        # Save to audio directory
        audio_dir = "audio"
        os.makedirs(audio_dir, exist_ok=True)
        
        audio_file_path = os.path.join(audio_dir, "hi_there.wav")
        
        with open(audio_file_path, "wb") as f:
            f.write(response.content)
        
        print(f"High-quality audio saved to: {audio_file_path}")
        print(f"File size: {len(response.content)} bytes")
        print("Voice: shimmer (warm, natural, human-like)")
        
        # Remove the old .aiff file if it exists
        old_file_path = os.path.join(audio_dir, "hi_there.aiff")
        if os.path.exists(old_file_path):
            os.remove(old_file_path)
            print(f"Removed old audio file: {old_file_path}")
        
        return audio_file_path
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        return None

def generate_multiple_voices():
    """Generate Hi There audio with different voices for comparison"""
    voices = [
        ("alloy", "Neutral, balanced voice"),
        ("echo", "Clear, professional voice"), 
        ("fable", "Expressive, storytelling voice"),
        ("onyx", "Deep, authoritative voice"),
        ("nova", "Energetic, engaging voice"),
        ("shimmer", "Warm, natural, human-like voice")
    ]
    
    # Load environment variables manually
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Load API key
    api_key = None
    try:
        with open("config/config.json", "r") as f:
            config = json.load(f)
            api_key = config.get("openai_api_key")
    except:
        pass
    
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("Error: OpenAI API key not found")
        return
    
    client = OpenAI(api_key=api_key)
    audio_dir = "audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    print("Generating Hi There audio with different voices for comparison...")
    
    for voice, description in voices:
        try:
            print(f"\nGenerating with {voice} voice ({description})...")
            
            response = client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input="Hi there!",
                response_format="wav",
                speed=1.0
            )
            
            audio_file_path = os.path.join(audio_dir, f"hi_there_{voice}.wav")
            
            with open(audio_file_path, "wb") as f:
                f.write(response.content)
            
            print(f"✓ Saved: {audio_file_path}")
            
        except Exception as e:
            print(f"✗ Error generating {voice}: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--compare":
        generate_multiple_voices()
    else:
        generate_hi_there_audio()