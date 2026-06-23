# 🧠 JARVIS-OS (Fable 5 V.A.U.L.T. Architecture)

> **Status: Production-Ready** | A 100% local, voice-driven AI command center and autonomous agentic OS running on any Windows machine.

JARVIS-OS is modeled on the decoupled Fable 5 OS framework. It handles multi-threaded local speech processing, cross-functional dynamic skill mapping, and persistent asynchronous long-term memory via local Markdown graphs.

---

## ⚡ Core System Architecture

* **The Brain (Skill Paradigm):** Orchestrated by **Gemini 2.5 Flash**. Native system scripts and dynamic skill subdirectories are evaluated, mapped, and appended to the LLM's functional execution scope at runtime.
* **The Memory (Obsidian Vault RAG):** Bypasses centralized relational databases. System events, commands, and structured reports are written as standalone `.md` files via local secure HTTPS REST channels.
* **The Voice (100% Offline Pipe):**
* **Ears (STT):** `faster-whisper-small.en` running on local CPU utilizing ahead-of-time ambient acoustic calibration to mitigate audio clipping.
* **Mouth (TTS):** `Kokoro v1.0` executing natively via ONNX runtimes to produce studio-grade natural human speech patterns without cloud overhead.


* **The Face (V.A.U.L.T. HUD):** A dedicated multi-threaded GUI built with `CustomTkinter`. Audio acquisition, orchestration processing, and text streaming execute on decoupled background threads to prevent main interface freezing.

---

## 🛠️ Installation & Setup

### 1. Pre-requisites

Ensure your system has **Python 3.12+** and the fast package manager **uv** installed. If you do not have uv, install it via PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

```

### 2. Workspace Initialization

Clone the repository, navigate to the root directory, and compile the isolated environment:

```bash
git clone https://github.com/BhargavaKandala/JARVIS-V0.1.git
cd JARVIS-V0.1
uv venv
uv pip install -r requirements.txt

```

### 3. Local Model Deployment

Jarvis operates 100% offline. To bypass manual Hugging Face searching, initialize the included setup downloader to fetch the speech assets:

```bash
uv run download_kokoro.py

```

> **Note:** Verify that `kokoro-v1.0.onnx` and `voices-v1.0.bin` are present in your workspace root before proceeding.

### 4. Mounting the Obsidian Brain

Initialize a clean local vault inside your Obsidian desktop app.

1. Navigate to **Settings** > **Community Plugins** and toggle "Restricted Mode" off.
2. Install, activate, and enable the **Local REST API** plugin.
3. Open the plugin configurations: Verify that the endpoint utilizes secure HTTPS (`https://127.0.0.1:27123`) and copy your unique alphanumeric API Key.

### 5. Runtime Environment Setup

Construct your personal execution settings profile by duplicating the production template:

```bash
cp .env.example .env

```

Open the newly created `.env` file and insert your respective authorization strings:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
OBSIDIAN_URL=https://127.0.0.1:27123
OBSIDIAN_API_KEY=your_copied_raw_api_key_here

```

> ⚠️ **Crucial:** Ensure no extra whitespaces, quotations, or strings like "Bearer" prefix the Obsidian token.

---

## 🚀 Ignition Sequence

With your Obsidian workspace active in the background, fire up the command interface:

```bash
uv run main.py

```

* Allow **2 seconds** for the workspace mic to adapt to ambient room acoustics.
* When the glowing kinetic particle engine initializes and reads **AWAITING AUDIO**, call out: *"Hey Jarvis..."*
* Instruct it: *"Jarvis, open YouTube and play a song"* or *"Jarvis, save a memory called Project Alpha and write down that local models are stable."*
