# import threading
# import time
# import customtkinter as ctk

# # Import your rock-solid Fable OS backend
# from voice.listener import listen
# from voice.speaker import speak
# from llm.gemini import ask_gemini, jarvis_tools

# # --- GUI THEME SETUP ---
# ctk.set_appearance_mode("dark")
# ctk.set_default_color_theme("blue")

# class VaultCommandCenter(ctk.CTk):
#     def __init__(self):
#         super().__init__()
        
#         self.title("J.A.R.V.I.S. - V.A.U.L.T. Command Center")
#         self.geometry("850x650")
#         self.resizable(False, False)

#         # --- HUD ELEMENTS ---
#         # 1. Header
#         self.header = ctk.CTkLabel(self, text="V.A.U.L.T. OS", font=("Consolas", 28, "bold"), text_color="#00FFCC")
#         self.header.pack(pady=(20, 5))

#         # 2. Live Status Indicator
#         self.status_label = ctk.CTkLabel(self, text="Status: Booting Cognitive Engine...", font=("Consolas", 16), text_color="yellow")
#         self.status_label.pack(pady=5)

#         # 3. Dynamic Skills Display
#         loaded_skills = [tool.name for tool in jarvis_tools]
#         skills_text = f"Active Branches: {len(jarvis_tools)} | Tools: {', '.join(loaded_skills)}"
#         self.skills_label = ctk.CTkLabel(self, text=skills_text, font=("Consolas", 12), text_color="#AAAAAA")
#         self.skills_label.pack(pady=(0, 15))

#         # 4. The Console (Transcript Box)
#         self.console = ctk.CTkTextbox(self, width=750, height=400, font=("Consolas", 14), corner_radius=10, fg_color="#1E1E1E")
#         self.console.pack(pady=10)
#         self.console.insert("0.0", "Initializing Fable 5 Architecture...\nLocal STT (Whisper) & TTS (Kokoro v1.0) linked.\nObsidian Memory Vault Mounted.\n\n")
#         self.console.configure(state="disabled") # Make it read-only

#         # --- THREADING ---
#         # Start the Voice AI on a separate thread so the GUI never freezes
#         self.ai_active = True
#         self.ai_thread = threading.Thread(target=self.event_loop, daemon=True)
#         self.ai_thread.start()

#     def log_to_console(self, speaker, message, color="#FFFFFF"):
#         """Safely writes text to the HUD console."""
#         self.console.configure(state="normal")
#         self.console.insert("end", f"[{speaker}] ", color)
#         self.console.insert("end", f"{message}\n\n")
#         self.console.see("end") # Auto-scroll to bottom
#         self.console.configure(state="disabled")

#     def update_status(self, status_text, hex_color):
#         """Updates the glowing status text."""
#         self.status_label.configure(text=f"Status: {status_text}", text_color=hex_color)

#     def event_loop(self):
#         """The main Fable OS logic loop running in the background."""
#         time.sleep(2) # Give the GUI a second to render
#         self.update_status("ONLINE - Waiting for Wake Word", "#00FF00")

#         while self.ai_active:
#             self.update_status("Listening...", "#00FFFF")
            
#             # 1. Ears
#             text = listen()

#             if text:
#                 self.log_to_console("USER", text)

#                 # 2. Wake Word Routing
#                 if any(word in text.lower() for word in ["jarvis", "jaress", "travis", "garbage"]):
#                     self.update_status("Processing...", "#FFA500")
#                     try:
#                         # 3. Brain (Gemini + Skill Router)
#                         response = ask_gemini(text)
#                         self.log_to_console("JARVIS", response)
                        
#                         # 4. Mouth (Kokoro)
#                         self.update_status("Speaking...", "#FF00FF")
#                         speak(response)
                        
#                     except Exception as e:
#                         error_msg = str(e)
#                         self.log_to_console("SYS_ERROR", error_msg)
                        
#                         if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
#                             speak("Boss, Google is rate limiting my API. Give me a moment to cool down.")
#                         else:
#                             speak("I encountered a critical error in my cognitive engine.")
#                 else:
#                     self.log_to_console("SYSTEM", "Wake word not detected. Audio discarded.")
            
#             self.update_status("ONLINE - Waiting for Wake Word", "#00FF00")

# if __name__ == "__main__":
#     app = VaultCommandCenter()
#     app.mainloop()



#############################################################################################################################
#############################################################################################################################

import threading
import time
import math
import random
import customtkinter as ctk

# Import your rock-solid Fable OS backend
from voice.listener import listen
from voice.speaker import speak
from llm.gemini import ask_gemini, jarvis_tools

# --- GUI THEME SETUP ---
ctk.set_appearance_mode("dark")

# Colors matching the image
BG_COLOR = "#050505"
PANEL_COLOR = "#0A0A0A"
TEXT_COLOR = "#A0A0A0"
ACCENT_COLOR = "#00E5FF" # Teal/Cyan
ALERT_COLOR = "#FF0055"
FONT_MAIN = ("Courier New", 12)
FONT_HEADER = ("Courier New", 14, "bold")
FONT_TITLE = ("Courier New", 24, "bold")

class VaultCommandCenter(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("V.A.U.L.T. - Jarvis OS")
        # Go fullscreen or large window to match the dashboard feel
        self.geometry("1400x800")
        self.configure(fg_color=BG_COLOR)

        # --- TOP HEADER ---
        self.top_frame = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0)
        self.top_frame.pack(side="top", fill="x", padx=20, pady=(20, 10))
        
        self.title_label = ctk.CTkLabel(self.top_frame, text="V.A.U.L.T.\nVOICE-ACTIVATED UNIFIED LOGIC TERMINAL", font=FONT_TITLE, text_color=TEXT_COLOR, justify="left")
        self.title_label.pack(side="left")

        self.status_nav = ctk.CTkLabel(self.top_frame, text="* CORE . IDLE    LINK . ONLINE    RUNNER . ALIVE", font=FONT_MAIN, text_color=ACCENT_COLOR)
        self.status_nav.pack(side="right", padx=20)

        # --- MAIN 3-COLUMN LAYOUT ---
        self.main_container = ctk.CTkFrame(self, fg_color=BG_COLOR)
        self.main_container.pack(fill="both", expand=True, padx=20, pady=10)

        # 1. LEFT PANEL (Vitals & Docs)
        self.left_panel = ctk.CTkFrame(self.main_container, fg_color=PANEL_COLOR, width=300)
        self.left_panel.pack(side="left", fill="y", padx=(0, 10))
        
        self.build_left_panel()

        # 2. CENTER PANEL (The Orb & Core Status)
        self.center_panel = ctk.CTkFrame(self.main_container, fg_color=BG_COLOR)
        self.center_panel.pack(side="left", fill="both", expand=True, padx=10)
        
        self.build_center_panel()

        # 3. RIGHT PANEL (Command Deck & Audio I/O)
        self.right_panel = ctk.CTkFrame(self.main_container, fg_color=PANEL_COLOR, width=350)
        self.right_panel.pack(side="right", fill="y", padx=(10, 0))
        
        self.build_right_panel()

        # --- THREADING & ANIMATION ---
        self.ai_active = True
        self.animate_orb()
        
        self.ai_thread = threading.Thread(target=self.event_loop, daemon=True)
        self.ai_thread.start()

    def build_left_panel(self):
        # System Vitals
        ctk.CTkLabel(self.left_panel, text="SYSTEM VITALS", font=FONT_HEADER, text_color=TEXT_COLOR).pack(anchor="w", pady=(10, 5), padx=10)
        self.memory_usage = ctk.CTkProgressBar(self.left_panel, progress_color=ACCENT_COLOR, fg_color="#1A1A1A", height=2)
        self.memory_usage.pack(fill="x", padx=10, pady=5)
        self.memory_usage.set(0.4)
        
        # Directives
        ctk.CTkLabel(self.left_panel, text="DIRECTIVES", font=FONT_HEADER, text_color=TEXT_COLOR).pack(anchor="w", pady=(30, 5), padx=10)
        directives = "> 1) Listen for Wake Word\n> 2) Route to Fable 5 OS\n> 3) Save to Obsidian"
        ctk.CTkLabel(self.left_panel, text=directives, font=FONT_MAIN, text_color=TEXT_COLOR, justify="left").pack(anchor="w", padx=10)

        # Documents (Obsidian Vault Preview)
        ctk.CTkLabel(self.left_panel, text="DOCUMENTS (VAULT)", font=FONT_HEADER, text_color=TEXT_COLOR).pack(anchor="w", pady=(30, 5), padx=10)
        self.docs_list = ctk.CTkLabel(self.left_panel, text="Master Plan.md\nProject Alpha.md\n", font=FONT_MAIN, text_color="#555555", justify="left")
        self.docs_list.pack(anchor="w", padx=10)

    def build_center_panel(self):
        # 2D Canvas to simulate the 3D Node Sphere
        self.canvas = ctk.CTkCanvas(self.center_panel, bg=BG_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # Particles for the "Orb"
        self.particles = [{"x": random.randint(-150, 150), "y": random.randint(-150, 150), "z": random.uniform(0.5, 2.0)} for _ in range(100)]
        self.angle = 0

        # Core Directive Status
        self.core_status_label = ctk.CTkLabel(self.center_panel, text="PRIMARY DIRECTIVE . IDLE", font=FONT_MAIN, text_color=TEXT_COLOR)
        self.core_status_label.pack(pady=(0, 5))
        
        self.main_state_label = ctk.CTkLabel(self.center_panel, text="AWAITING AUDIO", font=("Courier New", 48, "bold"), text_color=ACCENT_COLOR)
        self.main_state_label.pack(pady=(0, 20))

    def build_right_panel(self):
        # Command Deck
        ctk.CTkLabel(self.right_panel, text="COMMAND DECK", font=FONT_HEADER, text_color=TEXT_COLOR).pack(anchor="w", pady=(10, 5), padx=10)
        
        loaded_skills = [tool.name for tool in jarvis_tools]
        skills_text = "\n".join([f"+ {skill}" for skill in loaded_skills])
        ctk.CTkLabel(self.right_panel, text=skills_text, font=FONT_MAIN, text_color=ACCENT_COLOR, justify="left").pack(anchor="w", padx=10)

        # Audio I/O (Transcript)
        ctk.CTkLabel(self.right_panel, text="AUDIO I/O . TRANSCRIPT", font=FONT_HEADER, text_color=TEXT_COLOR).pack(anchor="w", pady=(30, 5), padx=10)
        
        self.console = ctk.CTkTextbox(self.right_panel, font=FONT_MAIN, fg_color="#111111", text_color=TEXT_COLOR, wrap="word", corner_radius=0)
        self.console.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.console.insert("0.0", "SYS> Audio engine active.\nSYS> Waiting for wake word...\n\n")
        self.console.configure(state="disabled")

    def animate_orb(self):
        """Simulates the rotating 3D node network on the canvas."""
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width > 10 and height > 10:
            cx, cy = width / 2, height / 2 - 50
            self.angle += 0.02
            
            # Draw rotating particles
            for p in self.particles:
                # Basic 3D to 2D projection rotation
                x = p["x"] * math.cos(self.angle) - p["z"] * 100 * math.sin(self.angle)
                y = p["y"]
                
                # Render dots
                if -200 < x < 200 and -200 < y < 200:
                    px = cx + x
                    py = cy + y
                    size = max(1, p["z"] * 1.5)
                    color = ACCENT_COLOR if random.random() > 0.8 else "#222222"
                    self.canvas.create_oval(px, py, px+size, py+size, fill=color, outline="")

        # Loop at ~30fps
        self.after(30, self.animate_orb)

    def log_to_console(self, speaker, message):
        self.console.configure(state="normal")
        color = ACCENT_COLOR if speaker == "JARVIS" else "#FFFFFF"
        if speaker == "SYS_ERROR": color = ALERT_COLOR
        
        # Insert tag, then message
        self.console.insert("end", f"{speaker}> ")
        self.console.insert("end", f"{message}\n\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def update_status(self, sub_text, main_text, color):
        self.core_status_label.configure(text=sub_text)
        self.main_state_label.configure(text=main_text, text_color=color)

    def event_loop(self):
        time.sleep(2)
        
        while self.ai_active:
            self.update_status("PRIMARY DIRECTIVE . IDLE", "AWAITING AUDIO", TEXT_COLOR)
            
            text = listen()

            if text:
                self.log_to_console("USER", text)

                if any(word in text.lower() for word in ["jarvis", "jaress", "travis", "garbage"]):
                    self.update_status("PRIMARY DIRECTIVE . ACTIVE", "PROCESSING", "#FFA500") # Orange
                    try:
                        response = ask_gemini(text)
                        self.log_to_console("JARVIS", response)
                        
                        self.update_status("PRIMARY DIRECTIVE . ACTIVE", "TRANSMITTING", ACCENT_COLOR) # Teal
                        speak(response)
                        
                    except Exception as e:
                        self.log_to_console("SYS_ERROR", str(e))
                        speak("I encountered a critical error in my cognitive engine.")

if __name__ == "__main__":
    app = VaultCommandCenter()
    app.mainloop()