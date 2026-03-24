import shutil
from config import ORG_DIR

def organize(files):
    organized = []

    for f in files:
        if not f["date"]:
            continue

        folder = ORG_DIR / f["date"].strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)

        target = folder / f["path"].name

        if not target.exists():
            shutil.move(str(f["path"]), target)

        f["organized_path"] = target
        organized.append(f)

    return organized