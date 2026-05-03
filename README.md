# 🗣️ Chummah — English Fluency Trainer

A fully local, ChatGPT-style English fluency trainer powered by Ollama. Voice in, voice out, real-time grammar & vocabulary corrections.

## ✨ Features

- **ChatGPT-style UI** — Dark mode, streaming responses, smooth animations
- **Two Modes** — Interview (STAR-method coaching) and Casual (friendly conversation)
- **Voice Input** — Click mic or press Space to speak (Web Speech API)
- **Voice Output** — Auto-reads bot responses aloud (SpeechSynthesis)
- **Real-time Corrections** — Grammar fixes, vocabulary tips, alternative phrasings
- **Session History** — All conversations saved locally in SQLite
- **100% Local** — No data leaves your machine

## 🚀 Quick Start

### Prerequisites
- [Ollama](https://ollama.com) installed and running
- Python 3.10+
- Chrome/Edge browser (for voice features)

### 1. Pull Models
```bash
ollama pull qwen2.5:7b
ollama pull mistral:7b
```

### 2. Start Ollama
```bash
ollama serve
```

### 3. Start Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Open Browser
Navigate to `http://localhost:8000`

## 🏗️ Project Structure

```
chummah/
├── backend/
│   ├── main.py              ← FastAPI app
│   ├── ollama_client.py     ← Ollama streaming + fallback
│   ├── prompt_builder.py    ← Mode-specific prompts
│   ├── db.py                ← SQLite database
│   └── requirements.txt
├── frontend/
│   ├── index.html           ← ChatGPT-clone UI
│   ├── style.css            ← Dark theme
│   └── app.js               ← Voice + chat + corrections
├── db/
│   └── chummah.db           ← Auto-created database
├── models/
│   └── README.md            ← Model documentation
└── README.md
```

## 🎯 Models

| Model | Role | Purpose |
|---|---|---|
| `qwen2.5:7b` | Primary | Best JSON output, strong English |
| `mistral:7b` | Backup | Reliable fallback |

## ⌨️ Keyboard Shortcuts

| Key | Action |
|---|---|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Space` (unfocused) | Toggle microphone |
