**Dashboard redesign** — *Fraunces* (serif display font, italic accents) paired with *DM Sans* for body text. Light cream page with white card surfaces, 1px rules, generous whitespace. The meeting IDs use monospace, scores use the serif numerals. Works in dark mode automatically via CSS variables. The vibe is editorial — like a refined internal tool, not a SaaS template.

**To integrate into your existing project**, drop the new files in:
```
your-project/
├── api_server.py              ← python api_server.py to start
├── requirements_api.txt       ← pip install -r requirements_api.txt
└── app/api/                   ← merge with your existing app/api/
    ├── main.py                ← new entry point
    ├── core/config.py         ← reads RAW_DATA_DIR, ORGANIZED_DATA_DIR etc
    ├── schema/schemas.py
    ├── services/              ← meetings, pipeline, analytics
    ├── routes/                ← 3 route files
    └── static/index.html      ← the dashboard
```

**Config** (`app/api/core/config.py`) defaults match your current structure — override via `.env` if your paths differ.

Ready for you to share `runner.py` and `llm_runner.py` so I can wire the subprocess calls exactly to their CLI signatures.