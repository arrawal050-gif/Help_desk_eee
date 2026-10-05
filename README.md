# Help_desk_eee

> **Sakhi (सखी)** — Smart Campus 360° Navigation & AI Voice Kiosk Guide for the Electrical & Electronics Engineering (EEE) Block, Shri Vaishnav Vidyapeeth Vishwavidyalaya (SVVV), Indore. Engineered with care by A.R. Labs.

---

## 🌟 Overview

**Sakhi** is an intelligent, hands-free kiosk guide designed to assist students, parents, faculty, and campus visitors in navigating the multi-floor EEE Block. Featuring interactive 360° panoramic virtual tours, synchronized Hinglish voice guidance, floor plans, and graph-based shortest-path routing, Sakhi ensures a seamless campus orientation experience.

---

## ✨ Features

- **Hands-Free Voice Recognition**: Listens for the wake word (*"Sakhi"* / *"सखी"*) and understands natural destination queries in Hindi, Hinglish, and English.
- **360° Virtual Tour Navigation**: High-resolution Three.js panorama viewer with smooth camera transitions and hotspot navigation.
- **Multi-Phase Hinglish Voice Guidance**: Powered by Microsoft Edge-TTS (`hi-IN-SwaraNeural`) delivering warm, natural audio synchronized with each transition node (Entry → Transition → Approach → Arrival).
- **Interactive Floor Plan Maps**: Visual 2D floor plans with live radar orientation cones and breadcrumb paths.
- **Live Calibration Admin Suite**: Visual 360° heading calibration tool (`/admin`) for aligning camera angles and landing orientations.
- **Vercel & Cloud Ready**: Fully packaged with serverless Python entry points and configuration for Vercel deployment.

---

## 🏗️ Architecture

```
help_desk_eee/
├── api/
│   └── index.py            # Vercel Serverless Python entrypoint
├── core/
│   ├── config.py           # Server & path constants
│   ├── entities.json       # Campus room & facility directory
│   ├── graph.py            # Navigation graph & Dijkstra router
│   ├── persona.py          # Sakhi character guidelines & system prompts
│   ├── resolver.py         # Fuzzy Hinglish destination resolver
│   ├── scene_calibration.json # Node camera orientation data
│   └── tts.py              # Microsoft Edge-TTS synthesis & tour segmentation
├── static/
│   ├── audio/              # Sound effects (feedback chime)
│   ├── css/                # Kiosk & admin styling
│   ├── js/                 # Three.js, Viewer, UI, & Kiosk controllers
│   ├── maps/               # High-res floor plan drawings
│   ├── panos/              # 360° equirectangular panoramas
│   ├── calibrate.html      # Visual calibration admin dashboard
│   └── index.html          # Main kiosk display interface
├── .env.example            # Environment variable & API key template
├── .gitignore              # Git ignore rules (secrets, venvs, cache)
├── main.py                 # FastAPI backend server
├── requirements.txt        # Python dependencies
├── vercel.json             # Vercel deployment routing
├── voice_listener.py       # Standalone voice daemon (for Raspberry Pi / Kiosk mic)
├── run_help_desk.bat       # Windows launcher
├── run_kiosk.bat           # Windows kiosk mode launcher
└── start_kiosk.sh          # Linux / Raspberry Pi launcher
```

---

## 🚀 Quickstart (Local Development)

### 1. Prerequisites
- Python 3.9+
- Git

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/arrawal050-gif/Help_desk_eee.git
cd Help_desk_eee

# Create a virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env` and fill in any necessary variables:
```bash
cp .env.example .env
```

### 4. Run the Web Server
```bash
python main.py
```
Open [http://localhost:8000](http://localhost:8000) in your browser.
To access the Calibration Suite: [http://localhost:8000/admin](http://localhost:8000/admin).

### 5. (Optional) Run Voice Daemon
For hands-free microphone listening on the kiosk hardware:
```bash
python voice_listener.py
```

---

## ☁️ Deploying to Vercel

1. Push your repository to GitHub.
2. Go to [Vercel Dashboard](https://vercel.com) and click **"Add New Project"**.
3. Import the `Help_desk_eee` repository.
4. In **Project Settings > Environment Variables**, add your configuration from `.env.example` if required (e.g. `API_BASE_URL`, external API keys).
5. Click **Deploy**. Vercel will automatically detect `vercel.json` and build the serverless application.

---

## 🔒 Security Notice

- **Never commit `.env` or sensitive API keys to GitHub.**
- The `.gitignore` file is preconfigured to prevent credentials, secrets, cache files, and local logs from being pushed.
- Store production API keys and credentials strictly in the Vercel Project Settings under **Environment Variables**.

---

## 📜 License
Developed for SVVV Indore. All rights reserved.
