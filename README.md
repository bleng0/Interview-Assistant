# 🎯 AI Interview Assistant

> **Practice interviews with AI-powered feedback** — Get real-time scoring, STAR method analysis, and personalized coaching powered by Google Gemini.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![React](https://img.shields.io/badge/react-18+-61DAFB.svg)
![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue.svg)

---

## 📋 Table of Contents

- [Features](#-features)
- [Demo](#-demo)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [User Guide](#-user-guide)
- [API Reference](#-api-reference)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

---

## ✨ Features

### Core Functionality
| Feature | Description |
|---------|-------------|
| 🎤 **Audio Recording** | Record your interview answers with real-time audio capture |
| 📝 **AI Transcription** | Automatic speech-to-text using Faster-Whisper (local, no API needed) |
| 🧠 **6-Score Analysis** | Content, Delivery, Communication, Voice, Confidence, Structure |
| 💡 **AI Coaching** | STAR method analysis and personalized improvement tips via Gemini |
| 📊 **Performance Tracking** | Session history, progress trends, and skill analytics |
| 📄 **Resume Analysis** | Match your resume against job descriptions |

### Interview Domains
- 💼 **Management** — Leadership & team scenarios
- 💻 **Software Engineering** — Technical & behavioral
- 💰 **Finance** — Analytical & situational  
- 📚 **Teaching** — Classroom & pedagogy
- 🛒 **Sales** — Client handling & negotiation

### Premium UI/UX
- 🌓 **Dark/Light Mode** — Beautiful themes with smooth transitions
- 📱 **Fully Responsive** — Works on desktop, tablet, and mobile
- ✨ **Animations** — Smooth micro-interactions and loading states
- 📈 **Interactive Charts** — Visual score breakdowns and trends

---

## 🚀 Quick Start

These steps take a fresh machine to a running app in about 30–45 minutes. Commands are for **Windows (PowerShell)**; macOS/Linux equivalents are in comments.

### 0. Prerequisites

| Tool | Version | Why | Check |
|------|---------|-----|-------|
| Python | 3.10–3.12 (3.12 recommended) | Backend | `python --version` |
| Node.js | 18+ | Frontend | `node --version` |
| FFmpeg | any recent | Converts browser audio (webm) to wav | `ffmpeg -version` |
| Java (JRE) | 17+ | LanguageTool grammar checker (optional; grammar scoring is skipped without it) | `java -version` |
| Git | any | Clone the repo | `git --version` |

Install on Windows with winget:
```powershell
winget install Python.Python.3.12 OpenJS.NodeJS.LTS Gyan.FFmpeg EclipseAdoptium.Temurin.17.JRE Git.Git
# macOS: brew install python@3.12 node ffmpeg openjdk@17 git
```
Restart the terminal afterwards so the new tools are on your PATH.

You also need:
- A **Supabase** project (free tier is fine): https://supabase.com/dashboard
- A **Google Gemini API key**: https://aistudio.google.com/apikey

### 1. Set up Supabase (one time)

1. **Create the schema.** In the Supabase dashboard, open **SQL Editor → New query**, paste the whole of `backend/database/final_schema.sql` and click **Run**.
   > ⚠️ This script **drops and recreates** all app tables. Run it only on a new project, or back up first.
   It creates 9 tables, row-level-security policies, triggers, sample questions, and the `audio-recordings` and `resumes` storage buckets.
2. **Check the buckets.** Under **Storage**, confirm `audio-recordings` and `resumes` exist and are **private**. If not, create them (the backend also tries to create them on startup).
3. **Configure email auth.** Under **Authentication → Providers**, make sure **Email** is enabled. For local testing you can turn off **Confirm email** so new sign-ups can log in straight away. Under **Authentication → URL Configuration**, set **Site URL** to `http://localhost:5173`.
4. **Copy three values** from **Project Settings → API** (or **API Keys**):
   - Project URL → `SUPABASE_URL` / `VITE_SUPABASE_URL`
   - `anon` public key → `SUPABASE_KEY` / `VITE_SUPABASE_ANON_KEY`
   - `service_role` secret key → `SUPABASE_SERVICE_ROLE_KEY` (**backend only — never put it in the frontend or commit it**)

### 2. Backend setup

```powershell
cd "AI-Interview-Assistant"          # repo root
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt      # first install is large (PyTorch, Whisper): 5–15 min
```
If PowerShell blocks the activate script, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Create `backend/.env` from the template and fill it in:
```powershell
cd backend
copy .env.example .env               # macOS/Linux: cp .env.example .env
```

```env
# --- LLM (required) ---
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=your_gemini_key
# Optional extra keys for rotation: LLM_API_KEY_2 ... LLM_API_KEY_12

# --- Transcription (local, no key) ---
TRANSCRIPTION_PROVIDER=faster_whisper
WHISPER_MODEL_SIZE=small             # tiny | base | small | medium (bigger = slower, more accurate)

# --- Supabase (required) ---
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_KEY=<anon public key>
SUPABASE_SERVICE_ROLE_KEY=<service_role secret key>

# --- Server ---
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
DEBUG=true                           # enables /docs; set false when deployed
ADMIN_EMAILS=you@example.com         # who may add/upload questions to the shared pool
```

### 3. Frontend setup

```powershell
cd ..\frontend
npm install
copy .env.example .env               # macOS/Linux: cp .env.example .env
```

```env
VITE_SUPABASE_URL=https://<your-project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon public key>
VITE_API_URL=http://localhost:8000
```

### 4. Run it (two terminals)

**Terminal 1 — backend** (from the repo root):
```powershell
.\venv\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --reload --port 8000
```
Wait for `API fully initialized and ready to accept requests`. The **first recorded answer** is slow (30–90 s) because Whisper, the sentence-transformer and LanguageTool models download on first use (~1 GB total, cached afterwards).

**Terminal 2 — frontend:**
```powershell
cd frontend
npm run dev
```

### 5. Check it works

| Check | Expected |
|-------|----------|
| http://localhost:8000/api/v1/health | JSON with `"status"` healthy |
| http://localhost:8000/docs | Interactive API docs |
| `python backend/check_gemini_quota.py` | Your Gemini key(s) respond |
| http://localhost:5173 | App loads; sign up, then log in |
| Record one answer | Scores + AI feedback appear in ~5–10 s (after the first-run download) |

### Common setup problems

| Symptom | Fix |
|---------|-----|
| Backend exits with `Supabase initialization failed` | Check `SUPABASE_URL` / keys in `backend/.env`; no quotes or spaces |
| Sign-up works but login says "Email not confirmed" | Confirm via the email link, or turn off **Confirm email** in Supabase Auth |
| Sessions/answers not saved | Schema not applied: re-run `final_schema.sql` on the project |
| `ffmpeg not found` / audio conversion errors | Install FFmpeg and restart the terminal |
| Grammar score always neutral | Java not installed (LanguageTool needs it) |
| Gemini `400 API key not valid` or `403` | Key revoked, blocked or unrestricted (see Troubleshooting); create a new key in AI Studio |
| API calls return `401` / `403` | You are logged out or the session expired: log in again. The backend only accepts requests carrying your login token |
| Admin question upload returns `403` | Add your account email to `ADMIN_EMAILS` in `backend/.env` and restart the backend |
| Frontend calls fail with CORS errors | Add the frontend URL to `CORS_ORIGINS` and restart the backend |

---

## 📁 Project Structure

```
AI Interview Assistant/
├── 📂 backend/
│   ├── app/
│   │   ├── api/v1.py              # REST API endpoints
│   │   ├── config.py              # Settings & constants
│   │   ├── main.py                # FastAPI application
│   │   └── services/
│   │       ├── ml_engine.py       # 6-score ML analysis
│   │       ├── llm_bridge.py      # Gemini AI integration
│   │       ├── transcript_service.py # Whisper transcription
│   │       ├── resume_service.py  # Resume parsing
│   │       └── supabase_db.py     # Database operations
│   ├── database/
│   │   └── final_schema.sql       # Supabase database schema
│   ├── check_gemini_quota.py      # API quota debugging tool
│   ├── test_key_rotation.py       # Multi-key testing tool
│   └── .env.example               # Environment template
│
├── 📂 frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx      # Main dashboard
│   │   │   ├── Recorder.tsx       # Audio recording
│   │   │   ├── FeedbackCard.tsx   # Score display
│   │   │   ├── HistoryTab.tsx     # Session history
│   │   │   └── InterviewSummary.tsx # Performance summary
│   │   ├── context/AuthContext.tsx # Authentication
│   │   ├── api/apiClient.ts       # TypeScript API client
│   │   ├── App.tsx                # Main application
│   │   └── styles/main.css        # Tailwind + custom CSS
│   └── .env.example               # Environment template
│
├── 📄 README.md                   # This file
├── 📄 docs/
│   ├── SETUP.md                   # Detailed setup guide
│   ├── USER_GUIDE.md              # How to use the app
│   └── API.md                     # API documentation
└── 📄 requirements.txt            # Python dependencies
```

---

## ⚙️ Configuration

### Backend Environment (`backend/.env`)

```env
# ===========================================
# LLM Configuration (Required)
# ===========================================
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
LLM_API_KEY=your_api_key_here

# Multiple keys for rotation (optional - comma separated)
# LLM_API_KEY=key1,key2,key3

# ===========================================
# Transcription (No API key needed)
# ===========================================
TRANSCRIPTION_PROVIDER=faster_whisper
WHISPER_MODEL_SIZE=small

# ===========================================
# Supabase Database (Required for persistence)
# ===========================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key
```

### Frontend Environment (`frontend/.env`)

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_public_key
```

### Scoring Weights

| Category | Weight | What It Measures |
|----------|--------|------------------|
| **Content** | 30% | Relevance to ideal answer (semantic similarity) |
| **Delivery** | 15% | Speaking pace (WPM), filler word count |
| **Communication** | 15% | Grammar, vocabulary diversity, coherence |
| **Voice** | 15% | Tone consistency and energy |
| **Confidence** | 15% | Composure and assertiveness |
| **Structure** | 10% | STAR method adherence |

---

## 📖 User Guide

### Starting an Interview

1. **Sign In** — Create an account or log in
2. **Select Domain** — Choose your interview category
3. **Enter Job Description** — Paste the JD for tailored questions
4. **Upload Resume** (Optional) — Get skills gap analysis
5. **Start Interview** — 10 questions (5 behavioral + 5 technical)

### Recording Answers

1. Click **"Start Recording"**
2. Speak your answer clearly
3. Click **"Stop"** when finished
4. Wait for AI analysis (~5-10 seconds)

### Understanding Your Scores

| Score | Meaning |
|-------|---------|
| 🟢 **80-100** | Excellent — Interview ready |
| 🟡 **60-79** | Good — Minor improvements needed |
| 🔴 **0-59** | Needs Work — Focus on these areas |

### Session Features

- **Skip Questions** — Skip and return later (shown with yellow badge)
- **Re-attempt** — Try any answered question again
- **Quick Navigation** — Sidebar shows progress
- **View Summary** — See overall performance after completing

### History & Analytics

- View all past sessions in the **History** tab
- Re-attempt completed sessions for more practice
- Download PDF reports for offline review
- Track improvement trends over time

---

## 🔌 API Reference

### Health Check
```
GET /api/v1/health
```
Returns system status and component health.

### Questions
```
GET /api/v1/questions/smart
  ?domain=software_engineering
  &difficulty=medium
  &count=10
```
Get interview questions for a domain.

### Submit Answer
```
POST /api/v1/submit_answer
Content-Type: multipart/form-data

audio_file: <audio.wav>
question: "Tell me about yourself"
ideal_answer: "Expected answer..."
session_id: "uuid"
question_id: "uuid"
```
Returns scores and AI feedback.

### Sessions
```
POST /api/v1/sessions/create    # Create new session
GET  /api/v1/sessions/{id}      # Get session details
POST /api/v1/sessions/{id}/skip # Skip a question
POST /api/v1/sessions/{id}/complete # Complete session
```

Full API documentation: http://localhost:8000/docs

---

## 🔧 Troubleshooting

### AI Feedback Not Working?

Run the quota checker:
```bash
cd backend
python check_gemini_quota.py
```

**Common Issues:**

| Error | Solution |
|-------|----------|
| `429 - Quota Exceeded` | Create new API key in [Google AI Studio](https://aistudio.google.com/apikey) |
| `400 - Invalid Key` | Verify key is correct, no extra spaces |
| `No response` | Check internet connection |

**Free Tier Limits:**
- 15 requests/minute
- 1,500 requests/day
- Resets at midnight Pacific Time

**Pro Tip:** Use multiple API keys for rotation:
```env
LLM_API_KEY=key1,key2,key3
```

### Audio Not Recording?

1. Allow microphone access in browser
2. Check browser console for errors
3. Try a different browser (Chrome recommended)

### Session Not Saving?

1. Verify Supabase credentials in `.env`
2. Check backend logs for database errors
3. Ensure database schema is applied

### Database Setup

Run the schema in Supabase SQL Editor:
```sql
-- Open backend/database/final_schema.sql
-- Copy and paste into Supabase SQL Editor
-- Click "Run"
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                │
│  React 18 + TypeScript + Tailwind CSS + Framer Motion          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ Auth Context │  │ API Client   │  │ Components            │ │
│  │ (Supabase)   │  │ (TypeScript) │  │ Dashboard, Recorder,  │ │
│  └──────────────┘  └──────────────┘  │ History, Summary      │ │
│                                      └───────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          BACKEND                                │
│  FastAPI + Python 3.10+                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ Whisper      │  │ ML Engine    │  │ LLM Bridge            │ │
│  │ Transcription│  │ (6 Scores)   │  │ (Gemini AI)           │ │
│  └──────────────┘  └──────────────┘  └───────────────────────┘ │
│                           │                                     │
│  ┌──────────────┬─────────┴──────────┬───────────────────────┐ │
│  │ Resume       │ Supabase           │ Question              │ │
│  │ Service      │ Database           │ Service               │ │
│  └──────────────┴────────────────────┴───────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User Records Answer** → Audio captured in browser
2. **Audio Uploaded** → Sent to backend via API
3. **Transcription** → Faster-Whisper converts speech to text
4. **ML Analysis** → 6 scores calculated locally
5. **AI Feedback** → Gemini generates coaching tips
6. **Results Stored** → Saved to Supabase database
7. **Display Feedback** → Shown in beautiful UI

---

## 🛡️ Security

- **Row Level Security (RLS)** — Users can only access their own data
- **Service Role Key** — Backend uses admin key, never exposed to client
- **Anon Key** — Frontend uses public key with RLS protection
- **No Audio Storage** — Audio processed and discarded (privacy first)

---

## 📦 Tech Stack

### Backend
- **FastAPI** — Modern Python web framework
- **Faster-Whisper** — Efficient local transcription
- **Sentence-Transformers** — Semantic similarity scoring
- **Google Gemini** — AI feedback generation
- **Supabase** — PostgreSQL database + Auth

### Frontend  
- **React 18** — UI framework
- **TypeScript** — Type safety
- **Tailwind CSS** — Utility-first styling
- **Framer Motion** — Animations
- **Lucide Icons** — Beautiful icons

---

## 📝 License

MIT License — Free for personal and educational use.

---

## 🙏 Acknowledgments

- **Google Gemini** — AI-powered feedback
- **Faster-Whisper** — Efficient transcription
- **Supabase** — Database and authentication
- **Tailwind CSS** — Beautiful styling

---

<p align="center">
  Made with ❤️ for job seekers everywhere
</p>
