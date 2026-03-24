from app.utils import log
import json
from app.llm.manager import get_llm
from app.llm.prompt import build_prompt

def process_json_files(files, tracker):
    for f in files:
        if f["type"] != "transcript":
            continue

        name = f["path"].name

        if name in tracker:
            log("skip", f"Already processed: {name}")
            continue

        try:
            log("process", f"Processing transcript: {name}")

            with open(f["organized_path"]) as fp:
                data = json.load(fp)

            log("llm", f"Running LLM on {name}")

            summary = run_llm(data)

            save_summary(f["organized_path"].parent, summary)

            tracker[name] = True

            log("success", f"Processed successfully: {name}")

        except Exception as e:
            log("error", f"{name} failed → {e}")



def run_llm(data):
    # llm = get_llm()

    # prompt = build_prompt(data)

    # log("llm", "Sending to LLM...")

    # response = llm.generate(prompt)
    # for attempt in range(3):
    #     try:
    #         return llm.generate(prompt)
    #     except Exception:
    #         log("warn", f"Retry {attempt+1}")
    return {
        # "raw": response,
        "summary": "Auto-generated summary",
        "length": len(str(data))
    }


def save_summary(folder, summary):
    out = folder / "summary.json"

    with open(out, "w") as f:
        json.dump(summary, f, indent=2)

    log("save", f"Saved summary → {out}")