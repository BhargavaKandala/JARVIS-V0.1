# # voice/listener.py
# import speech_recognition as sr
# from faster_whisper import WhisperModel
# import os

# print("Loading local Whisper model (This takes 3-5 seconds on CPU)...")
# # Upgraded to small.en for much better accuracy with accents and technical terms
# model = WhisperModel("small.en", device="cpu", compute_type="int8")
# recognizer = sr.Recognizer()

# # CALIBRATE ONLY ONCE AT STARTUP
# print("Calibrating microphone to your room's background noise...")
# with sr.Microphone() as source:
#     recognizer.adjust_for_ambient_noise(source, duration=2.0)
#     recognizer.pause_threshold = 1.5 # Wait 1.5s of silence before stopping

# def listen():
#     with sr.Microphone() as source:
#         print("\n[*] Listening... (Speak naturally)")
#         try:
#             # timeout: Wait 7s for you to start speaking
#             # phrase_time_limit: Let you talk for up to 20s
#             audio = recognizer.listen(source, timeout=7, phrase_time_limit=20)
#         except sr.WaitTimeoutError:
#             return ""

#     temp_filename = "temp_audio.wav"
#     with open(temp_filename, "wb") as f:
#         f.write(audio.get_wav_data())

#     # Fable OS Primer: Feed it expected vocabulary so it stops hallucinating
#     primer = "Jarvis, save a memory called Master Plan. Drone fleet, automated, web."
#     segments, info = model.transcribe(temp_filename, beam_size=5, initial_prompt=primer)
    
#     transcription = "".join([segment.text for segment in segments])
    
#     if os.path.exists(temp_filename):
#         os.remove(temp_filename)
        
#     final_text = transcription.strip()
#     junk_phrases = [".", "Thank you.", "Thanks.", "You", "Okay."]
#     if not final_text or final_text in junk_phrases or len(final_text) < 3:
#         return "" 
        
#     print(f"Heard: {final_text}")
#     return final_text


def listen():
    # Bypass the microphone entirely for a moment
    return input("\n[Type your command]: ")