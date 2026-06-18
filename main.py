import sys
from voice.listener import listen
from voice.speaker import speak
from voice.wakeword import detect_wake_word
from llm.gemini import ask_gemini

def main():
    speak("Jarvis is online. Waiting for wake word.")
    
    while True:
        # OUTER LOOP: Waiting for wake word
        text = listen()
        if not text:
            continue
            
        if detect_wake_word(text):
            speak("Yes Boss? I am listening.")
            
            # INNER LOOP: Continuous conversation
            while True:
                query = listen()
                if not query:
                    continue
                    
                # Commands to exit the program completely
                if query.lower() in ["exit", "quit", "shutdown"]:
                    speak("Goodbye.")
                    sys.exit()
                    
                # Command to put Jarvis back to sleep (wait for wake word again)
                if query.lower() in ["sleep", "stop listening", "mute"]:
                    speak("Going silent. Wake me if you need me.")
                    break # Breaks the inner loop, returns to outer loop
                    
                # If it's a regular question, ask Gemini
                response = ask_gemini(query)
                speak(response)

if __name__ == "__main__":
    main()