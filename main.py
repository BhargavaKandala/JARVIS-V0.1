import sys
from voice.listener import listen
from voice.speaker import speak
from voice.wakeword import detect_wake_word
from llm.gemini import ask_gemini

def main():
    speak("Hello, Jarvis is online. Waiting for wake word.")
    
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
                try:
                    response = ask_gemini(query)
                    speak(response)
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        speak("Boss, Google is rate limiting my API. Give me about 30 seconds to cool down.")
                    else:
                        print(f"[*] Brain Error: {error_msg}")
                        speak("I encountered a critical error in my cognitive engine.")

if __name__ == "__main__":
    main()