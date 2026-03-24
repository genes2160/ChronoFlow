from app.utils import log
import shutil
from config import ORG_DIR

def organize(files):
    organized = []

    for f in files:
        if not f["date"]:
            log("skip", f"Skipping (no date): {f['path'].name}")
            continue

        folder = ORG_DIR / f["date"].strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)

        target = folder / f["path"].name

        if not target.exists():
            shutil.move(str(f["path"]), target)
            log("move", f"{f['path'].name} → {folder.name}")
        else:
            log("skip", f"Already moved: {f['path'].name}")

        f["organized_path"] = target
        organized.append(f)

    return organized