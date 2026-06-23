# voice/speaker.py
import edge_tts
import pygame
import asyncio
import os

# This completely bypasses the pyttsx3 Windows loop crashes
async def _speak_async(text: str):
    print(f"Jarvis: {text}")
    voice = "en-US-ChristopherNeural" # High quality male voice
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save("temp_speech.mp3")

    pygame.mixer.init()
    pygame.mixer.music.load("temp_speech.mp3")
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    pygame.mixer.quit()
    os.remove("temp_speech.mp3")

def speak(text: str):
    """Wrapper to run the async TTS in the main loop."""
    asyncio.run(_speak_async(text))