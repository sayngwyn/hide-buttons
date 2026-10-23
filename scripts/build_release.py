"""Build the three edition zips for the release.

    python scripts/build_release.py

Runs build_editions.py and copies its zips to dist/nexus-upload/files/.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_editions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "nexus-upload"


def main():
    build_editions.main()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.zip"):  # zips from before the three editions lived here
        try:
            old.unlink()
        except PermissionError:
            print(f"could not remove {old.name} (in use by another program); ignore it, the real files are in files/")
    files = OUT / "files"
    shutil.rmtree(files, ignore_errors=True)
    files.mkdir()
    for zip_path in sorted(build_editions.OUT.glob("*.zip")):
        shutil.copy2(zip_path, files / zip_path.name)
        print(files / zip_path.name, zip_path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
