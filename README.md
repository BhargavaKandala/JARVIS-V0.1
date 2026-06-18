# 🧠 JARVIS-V0.1: The Foundation of an Autonomous Agentic Ecosystem

> *"Even in its infancy, this system redefines personal productivity, granting the user the privilege of frictionless, hands-free control over their digital environment. But this is only the beginning."*

## 🚀 Vision & Overview

JARVIS-V0.1 is a continuous, voice-activated AI assistant engineered to bridge the gap between human intent and machine execution. Powered by Google's **Gemini 2.5 Flash** and orchestrated via **LangChain**, this system transcends basic chatbots by actively controlling system functions and retrieving real-time data. 

While currently in its foundational `v0.1` stage, the architecture is built for infinite scalability. Right now, it acts as a highly capable digital proxy—giving the user the ultimate privilege of commanding web queries, system operations, and media playback entirely hands-free. In the future, this will evolve into a fully autonomous agentic system capable of deep logical reasoning, contextual memory, and proactive task orchestration.

## ✨ Core Capabilities (v0.1)

* **Always-On Wake Word Detection:** Operates silently in the background until summoned, ensuring zero friction when you need assistance.
* **Continuous Conversational Loop:** Maintains contextual awareness during a session. No need to repeat the wake word for follow-up questions.
* **Agentic Tool Calling:** Intelligently maps user intent to executable Python tools.
* **Real-Time Integrations:**
    * 🌐 **Web Browsing:** Opens specific websites on command.
    * ▶️ **Media Control:** Searches and plays YouTube content directly.
    * 🌤️ **Live Weather & News:** Fetches up-to-date global information.
    * 💻 **System Operations:** Can safely shut down the host system on voice command.

## 🛠️ Architecture

The system is decoupled into two primary pipelines for maximum efficiency:

1.  **The Sensory Loop (`main.py`):** Handles the continuous audio stream, wake-word detection (`detect_wake_word`), and speech-to-text processing. It features intelligent interrupt handling ("sleep", "mute") to pause the agent without killing the process.
2.  **The Cognitive Engine (`gemini.py`):** Utilizes LangChain's `bind_tools` paradigm to grant the LLM agency. It parses the transcribed text, decides if an external tool is required, executes the corresponding Python function, and formulates a natural language response.

## 📦 Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/YourUsername/JARVIS-V0.1.git
    cd JARVIS-V0.1
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Secure Your Credentials:**
    Create a `.env` file in the root directory. **Do not commit this file.** (Ensure `.gitignore` is active).
    ```env
    GOOGLE_API_KEY=your_gemini_api_key_here
    # Add OpenWeather or other API keys as needed
    ```

4.  **Initialize Jarvis:**
    ```bash
    python main.py
    ```

## 🎙️ Basic Commands

* *"Jarvis"* -> Wakes the system up.
* *"Play [Topic] on YouTube"* -> Executes the YouTube tool.
* *"What is the news today?"* -> Executes the News fetcher.
* *"Mute / Sleep / Stop listening"* -> Puts Jarvis back into standby mode.
* *"Exit / Shutdown"* -> Terminates the program completely.

## 🔮 The Road Ahead (Future Scope)

JARVIS-V0.1 lays the groundwork for a much larger architectural vision. Upcoming iterations will focus on transforming this reactive assistant into a proactive, multimodal agent:

* **Retrieval-Augmented Generation (RAG):** Integrating vector databases to allow Jarvis to read, remember, and query your personal documents and codebases autonomously.
* **Computer Vision Integration:** Granting Jarvis "sight" via real-time gesture recognition and screen context analysis (leveraging OpenCV/PyTorch).
* **Autonomous Task Orchestration:** Allowing Jarvis to schedule tasks, send communications, and handle complex, multi-step backend workflows.
* **Persistent Memory:** Maintaining long-term context across sessions to truly understand user preferences and project histories.

---
*Built to push the boundaries of daily productivity.*
