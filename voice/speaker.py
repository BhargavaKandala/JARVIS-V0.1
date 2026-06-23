# voice/speaker.py
import sounddevice as sd
from kokoro_onnx import Kokoro

print("Loading Kokoro v1.0 Voice Engine...")
# Initialize the local engine with the new v1.0 files
kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

def speak(text: str):
    """Generates 100% local, high-fidelity speech using Kokoro v1.0."""
    print(f"Jarvis: {text}")
    
    try:
        # Generate the audio array. "af_heart" is a great American Female voice.
        samples, sample_rate = kokoro.create(
            text, voice="af_heart", speed=1.0, lang="en-us"
        )
        
        # Play the audio synchronously through your speakers
        sd.play(samples, sample_rate)
        sd.wait() 
        
    except Exception as e:
        print(f"[*] Voice Engine Error: {e}")