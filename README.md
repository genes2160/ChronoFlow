# ChronoFlow
ChronoFlow is a lightweight media ingestion and processing pipeline that:

1. Scans a folder for incoming files
2. Detects file types (audio, video, transcript)
3. Extracts timestamps from filenames
4. Organizes files into daily folders
5. Processes transcript JSON files using an LLM
6. Stores structured outputs alongside original data
7. Tracks processed files to avoid duplication

---
## 📁 Folder Structure

project/
│
├── app/
├── data/
│   ├── raw/
│   └── organized/
├── logs/
├── runner.py
└── config.py

---

## ⚙️ Features

- Smart date extraction (ISO + Unix timestamps)
- Idempotent processing (no duplicates)
- Automatic folder organization by date
- JSON transcript → LLM → summary output
- Extendable architecture (FastAPI-ready)

---

## 🚀 How to Use

### 1. Drop files into:

data/raw/

Supported:
- `.webm` (audio/video)
- `.json` (transcripts)

---

### 2. Run:

```
python runner.py
```

---

### 3. Output Structure

data/organized/YYYY-MM-DD/

Example:

2026-03-24/
├── meeting-audio.webm
├── meeting-video.webm
├── transcript.json
├── summary.json

---

## 🔁 Idempotency

Processed files are tracked in:

logs/processed_files.json

Re-running the script will NOT reprocess files.

---

## 🧠 LLM Integration

Replace `run_llm()` in:

app/processor.py

with your OpenAI or other provider.

---

## 🧱 Future Upgrades

* File watcher (auto-trigger)
* FastAPI endpoints
* Celery async jobs
* PostgreSQL tracking
* Web dashboard

---

## 🧩 Philosophy

Start simple → scale only when necessary.

ChronoFlow is designed to evolve without rewriting the system.


---

# 🧠 TEXTUAL FLOWCHART

            ┌────────────────────┐
            │   data/raw/        │
            │  (incoming files)  │
            └─────────┬──────────┘
                      │
                      ▼
            ┌────────────────────┐
            │   scan_files()     │
            └─────────┬──────────┘
                      │
                      ▼
            ┌────────────────────┐
            │ normalize()        │
            │ - detect type      │
            │ - extract date     │
            └─────────┬──────────┘
                      │
                      ▼
            ┌────────────────────┐
            │ organize()         │
            │ move → YYYY-MM-DD  │
            └─────────┬──────────┘
                      │
                      ▼
            ┌────────────────────┐
            │ process_json()     │
            │ - read transcript  │
            │ - run LLM          │
            │ - save summary     │
            └─────────┬──────────┘
                      │
                      ▼
            ┌────────────────────┐
            │ update_tracker()   │
            │ (avoid duplicates) │
            └────────────────────┘