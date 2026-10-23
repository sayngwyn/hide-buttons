"""Build the three editions from src/HideButtons.py (the base edition) into dist/editions/.

    python scripts/build_editions.py

The editions are the same code with a different name, description and starting options (every option can still be
changed in MO2's Settings > Plugins), so only the block between the "edition" markers differs. Writes the three plugin
files and one zip each.
"""

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "HideButtons.py"
OUT = ROOT / "dist" / "editions"

ALL_OFF = {"hide_instance_manager": True, "hide_sort": True, "hide_unlock": False, "unlock_game_only": True,
           "hide_bulk_delete": False}
EDITIONS = {
    "HideButtons": ("Hide Buttons Plugin", "Hides the Manage Instances and Sort buttons.", ALL_OFF),
    "HideButtonsUnlock": ("Hide Buttons Plugin Unlock Edition",
                          "Hides the Manage Instances, Sort and Unlock buttons (Unlock for every program).",
                          {**ALL_OFF, "hide_unlock": True, "unlock_game_only": False}),
    "HideButtonsBiggieEdition": ("Hide Buttons Plugin Biggie Edition",
                                 "Hides Manage Instances, Sort, Unlock (only while the game or its script extender runs) "
                                 "and the bulk Delete Downloads menu entries.",
                                 {**ALL_OFF, "hide_unlock": True, "unlock_game_only": True, "hide_bulk_delete": True}),
}
BLOCK = re.compile(r"# ---- edition:.*?# ---- end edition\n", re.S)


def block(name, blurb, defaults):
    lines = ",\n            ".join(f'"{k}": {v}' for k, v in defaults.items())
    return ("# ---- edition: scripts/build_editions.py rewrites exactly this block to make the other two editions\n"
            f'NAME = "{name}"  # MO2 keys the saved settings on this: never rename it\n'
            f'BLURB = "{blurb}"\n'
            f"DEFAULTS = {{{lines}}}\n"
            "# ---- end edition\n")


def main():
    text = SOURCE.read_text(encoding="utf-8")
    assert BLOCK.search(text), "edition block not found in src/HideButtons.py"
    OUT.mkdir(parents=True, exist_ok=True)
    found = re.search(r"VersionInfo\((\d+),\s*(\d+),\s*(\d+)", text)
    assert found, "no VersionInfo in src/HideButtons.py"
    version = ".".join(found.groups())
    for stem, (name, blurb, defaults) in EDITIONS.items():
        built = BLOCK.sub(lambda _: block(name, blurb, defaults), text, count=1)
        (OUT / f"{stem}.py").write_text(built, encoding="utf-8", newline="\n")
        info = zipfile.ZipInfo(f"{stem}.py", date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        with zipfile.ZipFile(OUT / f"{stem}-{version}.zip", "w") as z:
            z.writestr(info, built.encode("utf-8"))
        print(f"{stem}-{version}.zip", name, defaults)


if __name__ == "__main__":
    main()
