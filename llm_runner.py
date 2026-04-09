import asyncio
from pathlib import Path
from pyexpat import model
import json, re
import time
from app.api.services.migration_service import migrate_summary, upsert_meeting
from app.api.services.migration_service import migrate_summary
from sqlmodel import select

from app.api.core.db import get_session
from app.api.models.model import LLMRequestLog, Meeting, Prompt, TranscriptTurn, Caption
from app.api.utils.prompt_config import get_data_hash
from app.utils import log
from app.llm.manager import get_llm
from app.llm.prompt import build_prompt
from config import LLM_PROVIDER
from app.utils import log

BASE_DIR = Path("data/organized")


def find_transcripts():
    transcripts = []

    # Iterate through the folders in the base directory
    for folder in BASE_DIR.iterdir():
        if not folder.is_dir():
            continue

        # Look for JSON files in each folder
        for file in folder.glob("*.json"):
            if "summary" in file.name:
                continue

            # Get the file size in bytes
            file_size = file.stat().st_size  # Get file size in bytes
            transcripts.append((file, file_size))  # Append the file and its size

    return transcripts


def select_files(files):
    print("\n📂 Available Transcripts:\n")

    # Print available files with their sizes
    for i, (f, size) in enumerate(files):
        size_in_kb = size / 1024  # Convert bytes to kilobytes
        print(f"[{i}] {f.parent.name} → {f.name} (Size: {size_in_kb:.2f} KB)")

    choice = input("\n👉 Select file(s) (e.g. 0 or 0,2): ")

    try:
        # Parse the selection and return the chosen files
        indexes = [int(x.strip()) for x in choice.split(",")]
        return [files[i][0] for i in indexes]  # Return just the file paths
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
        llm_provider=LLM_PROVIDER
        log("process", f"Processing {file_path.name}")
        log("debug", f"Full path: {file_path.resolve()}")
        log("debug", f"File exists: {file_path.exists()}")
        log("debug", f"File size: {file_path.stat().st_size} bytes")

        # read raw first to inspect
        raw = file_path.read_bytes()
        log("debug", f"Bytes around pos 1009: {raw[1000:1020]}")
        log("debug", f"Decoded around pos 1009: {raw[1000:1020].decode('utf-8', errors='replace')!r}")

        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)

        log("debug", f"JSON loaded successfully, keys: {list(data.keys())}")  # ← add this



        prompt = build_prompt(data)
        log("debug", f"prompt loaded: {type}")  # ← add this

        llm = get_llm(llm_provider)

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

        # ── new: also write to DB ──
        # _write_summary_to_db(file_path, parsed)
        
        return None
    except json.JSONDecodeError as e:
        log("error", f"{file_path.name} → JSON parse failed: {e}")
        log("debug", f"Error at: line {e.lineno}, col {e.colno}, pos {e.pos}")
        raw = file_path.read_bytes()
        log("debug", f"Raw bytes at error pos: {raw[e.pos-5:e.pos+15]}")
        log("debug", f"Decoded at error pos: {raw[e.pos-5:e.pos+15].decode('utf-8', errors='replace')!r}")
        return str(e)
    except Exception as e:
        log("error", f"{file_path.name} failed → {e}")
        log("debug", f"Exception type: {type(e).__name__}")
        return str(e)

def run_llm_on_datameeting_dbprompt(meeting_id: str, date: str, data: dict):
    try:
        from sqlmodel import Session
        from app.api.core.db import engine
        from app.api.services.migration_service import upsert_meeting, migrate_summary

        log("process", f"Processing meeting {meeting_id}")

        prompt = build_prompt(data)
        llm = get_llm(LLM_PROVIDER)

        log("llm", "Sending to LLM...")
        response = llm.generate(prompt)
        parsed = parse_response(response)

        with Session(engine) as session:
            meeting = upsert_meeting(session, meeting_id, date)
            if meeting:
                migrate_summary(session, meeting, {"response": parsed})
                session.commit()
                log("db", f"Written to DB → {meeting_id}")

        return None
    except Exception as e:
        log("error", f"{meeting_id} failed → {e}")
        log("debug", f"Exception type: {type(e).__name__}")
        return str(e)

async def run_llm_on_data(meeting_id: str, date: str, data: dict, prompt_name: str = "summarize_meeting", prompt_version: str = "1.0"):
    """Run LLM for a meeting using prompts stored in DB (provider+model in prompt)"""
    # 2️⃣ Load prompts from DB
    with get_session() as session:
        prompt = session.exec(
            select(Prompt).where(Prompt.name == prompt_name, Prompt.version == prompt_version)
        ).first()

    if not prompt:
        log("error", f"No prompts found for {prompt_name} v{prompt_version}")
        return f"No prompts found"

    llm_provider=LLM_PROVIDER
    llm_instance = get_llm(llm_provider)
    prompt_text = prompt.text  # **from DB, not file**

    data_hash = get_data_hash(data)

    # Deduplication: skip if already processed
    with get_session() as session:
        existing = session.exec(
            select(LLMRequestLog).where(
                LLMRequestLog.prompt_id == prompt.id,
                LLMRequestLog.meeting_id == meeting_id,
                LLMRequestLog.provider == llm_provider,
                LLMRequestLog.model == llm_instance.model_name(),
                LLMRequestLog.data_hash == data_hash
            )
        ).first()
        # if existing:
        #     log("warn", f"Already processed {meeting_id} with {llm_provider}/{llm_instance.model_name()}")
        #     return str(f"Already processed {meeting_id} with {llm_provider}/{llm_instance.model_name()}")

    # 3️⃣ Prepare final prompt (insert transcript JSON)
    filled_prompt = prompt_text.replace("<transcript>", json.dumps(data, indent=2))
    log("debug", f"Filled prompt for {meeting_id}:\n{filled_prompt[:100]}...")  # log the first 500 chars of the prompt
    # 4️⃣ Run LLM
    start = time.time()
    try:
        response = await asyncio.to_thread(llm_instance.generate, filled_prompt)
        duration = time.time() - start
        log("llm", f"Processed {meeting_id} with {llm_provider}/{model} in {duration:.2f}s")
    except Exception as e:
        log("error", f"LLM failed for {meeting_id} with {llm_provider}/{model} → {e}")
        return str(f"LLM failed for {meeting_id} with {llm_provider}/{model} → {e}")
    # 5️⃣ Save success to DB
    with get_session() as session:
        if existing:
            log("warn", f"Duplicate detected for {meeting_id} with {llm_provider}/{model}, skipping DB write")
        else:
            log_entry = LLMRequestLog(
                prompt_id=prompt.id,
                meeting_id=meeting_id,
                provider=llm_provider,
                model=llm_instance.model_name(),
                data=data,
                data_hash=data_hash,
                response=response,
                duration_sec=duration,
            )
            session.add(log_entry)
            session.commit()

        parsed = parse_response(response)

        with get_session()  as session:
            meeting = upsert_meeting(session, meeting_id, date)
            if meeting:
                migrate_summary(session, meeting, {"response": parsed})
                session.commit()
                log("db", f"Written to DB → {meeting_id}")
                
    return {"meeting_id": meeting_id, "provider": llm_provider, "model": llm_instance.model_name(), "duration_sec": duration}


def _write_summary_to_db(file_path: Path, parsed: dict) -> None:
    """
    Write LLM output to DB after saving to disk.
    Extracts meeting_id and date from the file's parent folder path.
    Silent on failure — disk write already succeeded, DB is additive.
    """
    try:
        from sqlmodel import Session
        from app.api.core.db import engine
        from app.api.services.migration_service import (
            upsert_meeting, migrate_summary
        )

        date      = file_path.parent.name          # folder is the date
        meeting_id = _extract_meeting_id_from_path(file_path)

        if not meeting_id:
            log("warn", f"Could not extract meeting_id from {file_path.name}, skipping DB write")
            return

        with Session(engine) as session:
            meeting = upsert_meeting(session, meeting_id, date)
            if meeting:
                migrate_summary(session, meeting, {"response": parsed})
                session.commit()
                log("db", f"Written to DB → {meeting_id}")
    except Exception as e:
        log("warn", f"DB write failed (disk write OK): {e}")


def _extract_meeting_id_from_path(file_path: Path) -> str | None:
    import re
    match = re.search(r'([a-z]{3}-[a-z]{4}-[a-z]{3})', file_path.name)
    return match.group(1) if match else None


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