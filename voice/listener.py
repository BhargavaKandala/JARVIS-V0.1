# voice/listener.py
import speech_recognition as sr
from faster_whisper import WhisperModel
import os

print("Loading local Whisper model (This takes 3-5 seconds on CPU)...")
# small.en is highly accurate for accents and tech jargon
model = WhisperModel("small.en", device="cpu", compute_type="int8")
recognizer = sr.Recognizer()

# CALIBRATE ONLY ONCE AT STARTUP
print("Calibrating microphone to your room's background noise (Please stay quiet for 2 seconds)...")
with sr.Microphone() as source:
    recognizer.adjust_for_ambient_noise(source, duration=2.0)
    # 1.5 seconds of silence needed before it stops recording your sentence
    recognizer.pause_threshold = 1.5 

def listen():
    with sr.Microphone() as source:
        print("\n[*] Listening... (Speak naturally)")
        try:
            # Wait up to 7s for you to start speaking, allow up to 20s of continuous talking
            audio = recognizer.listen(source, timeout=7, phrase_time_limit=20)
        except sr.WaitTimeoutError:
            return ""

    temp_filename = "temp_audio.wav"
    with open(temp_filename, "wb") as f:
        f.write(audio.get_wav_data())

    # The Primer: Tells Whisper what kind of words to expect so it doesn't hallucinate
    primer = "Jarvis, save a memory called Master Plan. Drone fleet, automated, weather, youtube."
    segments, info = model.transcribe(temp_filename, beam_size=5, initial_prompt=primer)
    
    transcription = "".join([segment.text for segment in segments])
    
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
        
    final_text = transcription.strip()
    
    # Filter out common Whisper hallucinations
    junk_phrases = [".", "Thank you.", "Thanks.", "You", "Okay.", "Thanks for watching!"]
    if not final_text or final_text in junk_phrases or len(final_text) < 3:
        return "" 
        
    print(f"Heard: {final_text}")
    return final_text