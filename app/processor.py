from app.utils import log, STATUS
import json
from app.llm.manager import get_llm
from app.llm.prompt import build_prompt

def process_json_files(files, tracker):
    success_count = 0
    skipped_count = 0
    failed_count = 0
    for f in files:
        if f["type"] != "transcript":
            continue

        name = f["path"].name

        if name in tracker:
            log("skip", f"Already processed: {name}")
            skipped_count += 1
            continue

        try:
            log("process", f"Processing transcript: {name}")

            with open(f["organized_path"]) as fp:
                data = json.load(fp)

            log("llm", f"Running LLM on {name}")

            tracker[name] = True

            log("success", f"Processed successfully: {name}")
            success_count+=1
        except Exception as e:
            log("error", f"{name} failed → {e}")
            failed_count+=1
    return {
        "status": STATUS["completed"],
        "message": f"Processed {success_count}, failed {failed_count} and skipped {skipped_count} records out of {len(files)}"
    }


def get_summary(folder):
    out = folder / "summary.json"
    if not out.exists():
        return []

    try:
        with open(out, encoding="utf8") as f:
            content = f.read().strip()

            if not content:
                return []

            return json.loads(content)

    except json.JSONDecodeError:
        print("⚠️ Summary file corrupted. Resetting...")
        return []


def save_summary(folder, summary):
    out = folder / "summary.json"

    with open(out, "w") as f:
        json.dump(summary, f, indent=2)

    log("save", f"Saved summary → {out}")