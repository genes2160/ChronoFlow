import json

def process_json_files(files, tracker):
    for f in files:
        if f["type"] != "transcript":
            continue

        name = f["path"].name

        if name in tracker:
            continue

        try:
            with open(f["organized_path"]) as fp:
                data = json.load(fp)

            summary = run_llm(data)

            save_summary(f["organized_path"].parent, summary)

            tracker[name] = True

        except Exception as e:
            print(f"Error processing {name}: {e}")


def run_llm(data):
    # Replace with real LLM
    return {
        "summary": "Auto-generated summary",
        "length": len(str(data))
    }


def save_summary(folder, summary):
    out = folder / "summary.json"

    with open(out, "w") as f:
        json.dump(summary, f, indent=2)