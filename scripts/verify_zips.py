"""Check that each release zip holds exactly the edition file that was tested (dist/editions/<name>.py)."""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bad = 0
for z in sorted((ROOT / "dist" / "nexus-upload" / "files").glob("*.zip")):
    name = z.stem.rsplit("-", 1)[0]
    with zipfile.ZipFile(z) as zf:
        same = zf.namelist() == [name + ".py"] and zf.read(name + ".py") == (ROOT / "dist" / "editions" / (name + ".py")).read_bytes()
    print(z.name, "matches" if same else "DIFFERS")
    bad += not same
sys.exit(1 if bad else 0)
