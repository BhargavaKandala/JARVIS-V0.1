# voice/speaker.py
import pyttsx3

def speak(text: str):
    print(f"Jarvis: {text}")
    engine = pyttsx3.init()
    
    voices = engine.getProperty('voices')
    
    # Change index to 1 for the female voice (Microsoft Zira)
    # If 1 throws an error, you can loop through `voices` and print their names to find the exact index.
    if len(voices) > 1:
        engine.setProperty('voice', voices[1].id) 
    else:
        engine.setProperty('voice', voices[0].id)
        
    engine.setProperty('rate', 170) # Slightly slower often sounds more natural
    
    engine.say(text)
    engine.runAndWait()