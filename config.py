from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

RAW_DIR = Path("data/raw")
ORG_DIR = Path("data/organized")
LOG_DIR = Path("logs")

TRACK_FILE = LOG_DIR / "processed_files.json"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
JINA_API_KEY = os.getenv("JINA_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL_MAP = {
    "openrouter": "openai/gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "jina": "jina-chat",
    "anthropic": "claude-sonnet-4-6",
}

LOG_DIR.mkdir(exist_ok=True)
ORG_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
