# voice/listener.py
import speech_recognition as sr
from faster_whisper import WhisperModel
import os

print("Loading local Whisper model...")
# Load the model once globally so it doesn't reload on every sentence
model = WhisperModel("base.en", device="cpu", compute_type="int8")
recognizer = sr.Recognizer()

def listen():
    """Dynamically listens until the user stops speaking, then transcribes locally."""
    with sr.Microphone() as source:
        # Dynamically adjust to ambient background noise
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("\n[*] Listening... (Speak naturally)")
        
        try:
            # timeout: How long to wait for you to START speaking
            # phrase_time_limit: Max duration of a single sentence
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            # Nobody said anything within 5 seconds
            return ""

    # Save the smart-cropped audio to a temporary file
    temp_filename = "temp_audio.wav"
    with open(temp_filename, "wb") as f:
        f.write(audio.get_wav_data())

    # Transcribe locally with Whisper
    segments, info = model.transcribe(temp_filename, beam_size=5)
    
    transcription = ""
    for segment in segments:
        transcription += segment.text
        
    # Clean up the temp file
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
        
    final_text = transcription.strip()
    if final_text:
        print(f"Heard: {final_text}")
        
    return final_text