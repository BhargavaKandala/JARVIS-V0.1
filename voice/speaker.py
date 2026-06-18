import pyttsx3

engine = pyttsx3.init()
engine.setProperty("rate", 180)

def speak(text: str):
    print(f"\nJarvis: {text}\n")
    engine.say(text)
    engine.runAndWait()