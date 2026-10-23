"""Run a test-only harness inside the portable test MO2 and put the MO2 folder back as it was.

    python tests/live/run_live.py --harness probe.py [--plugin src/HideButtons.py] [--config key=value ...]

Refuses if this MO2 already runs or if any game process runs (MO2 must not start programs while a game runs).
Copies the harness (and optionally the plugin) into ``test-env/MO2/plugins``, starts MO2 with ``--multiple``, waits for it
to exit, removes what it added, restores ModOrganizer.ini and the profile files, and prints what changed.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MO2 = REPO / "test-env" / "MO2"
SKIP_DIRS = {"logs", "crashDumps", "webcache"}
GAMES = ("SkyrimSE", "Skyrim", "Fallout4", "Fallout4VR", "SkyrimVR", "Starfield")


def running(names: str) -> list[str]:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-Process {names} -ErrorAction SilentlyContinue | ForEach-Object {{ $_.Path }}"],
                         capture_output=True, creationflags=0x08000000, text=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def mo2_running() -> bool:
    mine = str((MO2 / "ModOrganizer.exe").resolve()).lower()
    return any(p.lower() == mine for p in running("ModOrganizer"))


def game_folders() -> list[Path]:
    """The game folder this MO2 points at and the game's Documents\\My Games folder, to prove a run left them alone."""
    out = []
    for line in (MO2 / "ModOrganizer.ini").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("gamePath="):
            value = line.split("=", 1)[1].strip()
            if value.startswith("@ByteArray(") and value.endswith(")"):
                value = value[len("@ByteArray("):-1]
            out.append(Path(value.replace("\\\\", "\\")))
        if line.startswith("gameName="):
            name = line.split("=", 1)[1].strip()
    docs = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('MyDocuments')"],
                          capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
    if docs:
        out.append(Path(docs) / "My Games" / name)
    return [p for p in out if p.is_dir()]


def snapshot(root: Path) -> dict[str, int]:
    out = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] in SKIP_DIRS or "__pycache__" in rel.parts:
            continue  # MO2 compiles its own Python plugins on start
        if p.is_file():
            out[str(rel)] = p.stat().st_size
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True, type=Path)
    ap.add_argument("--plugin", type=Path, help="the plugin file under test")
    ap.add_argument("--config", nargs="*", default=[], help="key=value pairs written to harness_config.json")
    ap.add_argument("--profile", default="Default")
    ap.add_argument("--multiple", action="store_true", help="accepted for clarity: MO2 is always started with --multiple")
    ap.add_argument("--mo2-exe", type=Path, help="the test MO2's own program file, spelled out (checked against test-env/MO2)")
    ap.add_argument("--lock-program", action="store_true", help="add Character Map as a 'Stay Probe' program (it only keeps MO2 in its locked state) to MO2's executables")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()

    if a.mo2_exe and a.mo2_exe.resolve() != (MO2 / "ModOrganizer.exe").resolve():
        sys.exit(f"--mo2-exe is not this repo's test MO2: {a.mo2_exe}")
    plugins = MO2 / "plugins"
    if not (MO2 / "ModOrganizer.exe").is_file() or not (MO2 / "portable.txt").is_file():
        sys.exit(f"not a portable MO2: {MO2}")
    if mo2_running():
        sys.exit("this test MO2 is already running")
    if running(",".join(GAMES)):
        sys.exit("a game is running; not starting any program through MO2 now")

    harness = a.harness.resolve()
    deploy = [(harness, plugins / harness.name), (None, plugins / "harness_config.json")]
    if a.plugin:
        deploy.append((a.plugin.resolve(), plugins / a.plugin.name))
    for _, dest in deploy:
        if dest.exists():
            sys.exit(f"already present, refusing to overwrite: {dest}")

    profile = MO2 / "profiles" / a.profile
    guarded = [MO2 / "ModOrganizer.ini"] + [p for p in profile.iterdir() if p.is_file()]
    backup = REPO / "results" / f"backup-{time.strftime('%H%M%S')}"
    backup.mkdir(parents=True)
    for p in guarded:
        shutil.copy2(p, backup / (p.name if p.parent == profile else "_root_" + p.name))
    before = snapshot(MO2)
    watched = game_folders()
    started = time.time() - 2  # file times can round down
    results = REPO / "results" / (harness.stem + ".json")
    results.unlink(missing_ok=True)
    cfg = dict(kv.split("=", 1) for kv in a.config) | {"results": str(results)}

    if a.lock_program:  # the ini is restored from the backup afterwards
        ini = MO2 / "ModOrganizer.ini"
        ini.write_text(ini.read_text(encoding="utf-8") + "\n[customExecutables]\nsize=1\n1\\title=Stay Probe\n1\\toolbar=false\n"
                       "1\\ownicon=false\n1\\binary=C:/Windows/System32/charmap.exe\n1\\arguments=\n"
                       "1\\workingDirectory=\n1\\steamAppID=\n1\\hide=false\n", encoding="utf-8")
    for src, dest in deploy:
        if src is None:
            dest.write_text(json.dumps(cfg), encoding="utf-8")
        else:
            shutil.copy2(src, dest)
    report: dict = {}
    try:
        proc = subprocess.Popen([str(MO2 / "ModOrganizer.exe"), "--multiple", "-p", a.profile], cwd=str(MO2))
        try:
            report["exit_code"] = proc.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            report["exit_code"] = "TIMEOUT: MO2 still running; closing it"
            proc.terminate()
            proc.wait(timeout=20)
    finally:
        if not mo2_running():
            for _, dest in deploy:
                dest.unlink(missing_ok=True)

    for p in guarded:
        saved = backup / (p.name if p.parent == profile else "_root_" + p.name)
        if not filecmp.cmp(saved, p, shallow=False):
            shutil.copy2(saved, p)
            report.setdefault("restored", []).append(str(p.relative_to(MO2)))
    shutil.rmtree(backup)
    after = snapshot(MO2)
    changed = [str(p) for folder in watched for p in folder.rglob("*") if p.is_file() and p.stat().st_mtime >= started]
    report["game_files_changed_during_run"] = changed[:40]
    report.update(added=sorted(set(after) - set(before)), removed=sorted(set(before) - set(after)))
    if results.is_file():
        report["harness"] = json.loads(results.read_text(encoding="utf-8"))
    print(json.dumps(report, indent=1))
    return 0 if report.get("harness", {}).get("passed", True) else 1


if __name__ == "__main__":
    sys.exit(main())
