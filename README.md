# 🧠 JARVIS-OS (Fable 5 Architecture)

> *"A 100% local, voice-driven AI command center and autonomous agentic OS."*

JARVIS-OS is a next-generation personal assistant built on the Fable 5 OS architecture. It abandons traditional, cloud-dependent, hardcoded chatbot scripts in favor of **100% local voice processing**, **dynamic skill routing**, and a **persistent Obsidian markdown memory vault**.

## ✨ Core Features

* 🎙️ **100% Local Voice Pipeline:** * **Ears (STT):** Uses `faster-whisper` (`small.en`) running locally on CPU. Smart ambient noise calibration prevents audio clipping and hallucination.
  * **Mouth (TTS):** Powered by **Kokoro v1.0**, delivering ultra-realistic, human-level speech synthesis entirely offline.
* 🗄️ **The Memory Vault (Obsidian RAG):** * Bypasses complex databases. Jarvis reads and writes plain `.md` files directly to a local Obsidian vault via the Local REST API. It remembers your master plans, preferences, and ideas forever.
* 🧩 **Dynamic Skill Architecture (The Brain):**
  * Built with LangChain and Gemini 2.5 Flash. Tools are no longer hardcoded. Drop a new Python file into the `skills/` folder, and Jarvis automatically learns the new capability on startup.

---

## 🛠️ Setup & Installation

### 1. Prerequisites
* Python 3.12+
* [uv](https://github.com/astral-sh/uv) (Extremely fast Python package manager)
* [Obsidian](https://obsidian.md/) (For the memory vault)

### 2. Environment Setup
Clone the repo and install dependencies instantly using `uv`:
```bash
git clone [https://github.com/BhargavaKandala/JARVIS-V0.1.git](https://github.com/BhargavaKandala/JARVIS-V0.1.git)
cd JARVIS-V0.1
uv venv
uv pip install -r requirements.txt