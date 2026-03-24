from pathlib import Path
import json, re

from app.utils import log
from app.llm.manager import get_llm
from app.llm.prompt import build_prompt

BASE_DIR = Path("data/organized")


def find_transcripts():
    transcripts = []

    for folder in BASE_DIR.iterdir():
        if not folder.is_dir():
            continue

        for file in folder.glob("*.json"):
            if file.name == "summary.json":
                continue

            transcripts.append(file)

    return transcripts


def select_files(files):
    print("\n📂 Available Transcripts:\n")

    for i, f in enumerate(files):
        print(f"[{i}] {f.parent.name} → {f.name}")

    choice = input("\n👉 Select file(s) (e.g. 0 or 0,2): ")

    try:
        indexes = [int(x.strip()) for x in choice.split(",")]
        return [files[i] for i in indexes]
    except Exception:
        print("❌ Invalid selection")
        return []


def parse_response(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # sometimes the model wraps in an outer key e.g. {"response": {...}}
        try:
            wrapper = json.loads(text)
            if isinstance(wrapper, dict) and len(wrapper) == 1:
                inner = next(iter(wrapper.values()))
                if isinstance(inner, dict):
                    return inner
        except Exception:
            pass

        # last resort: find the first { ... } block in the text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())

        raise ValueError(f"Could not parse LLM response as JSON:\n{text[:300]}")


def run_llm_on_file(file_path):
    try:
        log("process", f"Processing {file_path.name}")

        with open(file_path) as f:
            data = json.load(f)

        prompt = build_prompt(data)
        llm = get_llm()

        log("llm", "Sending to LLM...")
        response = llm.generate(prompt)

        parsed = parse_response(response)

        from datetime import datetime
        name = file_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = file_path.parent / f"{name}_summary_{timestamp}.json"

        with open(output_path, "w") as f:
            json.dump({"response": parsed}, f, indent=2)

        log("save", f"Saved → {output_path}")
        log("success", f"Done: {file_path.name}")

    except json.JSONDecodeError as e:
        log("error", f"{file_path.name} → JSON parse failed: {e}")
    except Exception as e:
        log("error", f"{file_path.name} failed → {e}")


def main():
    log("scan", "Scanning organized folders...")

    transcripts = find_transcripts()

    if not transcripts:
        log("warn", "No transcripts found")
        return

    selected = select_files(transcripts)

    if not selected:
        log("warn", "No files selected")
        return

    for file in selected:
        run_llm_on_file(file)

    log("success", "LLM run complete")


if __name__ == "__main__":
    main()