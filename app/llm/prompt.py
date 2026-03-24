import re
import json
from pathlib import Path

def build_prompt(transcript) -> str:
    prompt = Path("meeting_analysis_prompt_v2.md").read_text()
    text = json.dumps(transcript, indent=2) if isinstance(transcript, (dict, list)) else transcript
    prompt = re.sub(r"<transcript>.*?</transcript>",
                  f"<transcript>\n{text}\n</transcript>",
                  prompt, flags=re.DOTALL)
    return prompt