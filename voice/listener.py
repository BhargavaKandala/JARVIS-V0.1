import speech_recognition as sr
from config.settings import FORCE_TEXT_MODE

def listen() -> str:
    # If forced text mode is active, completely bypass the hardware layer
    if FORCE_TEXT_MODE:
        text = input("You (Type here): ")
        return text

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("\nListening (Speak now)...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            text = recognizer.recognize_google(audio)
            print(f"You (Voice): {text}")
            return text
            
    except (OSError, AttributeError, sr.RequestError):
        print("\n[Microphone hardware error. Switching to Text Mode]")
        text = input("You (Type here): ")
        return text
        
    except (sr.WaitTimeoutError, sr.UnknownValueError):
        return ""
    except Exception as e:
        print(f"Error: {e}")
        return ""