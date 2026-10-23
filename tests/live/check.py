"""Test-only MO2 plugin: checks Hide Buttons inside a real MO2 (never shipped).

Copied into the test MO2 by ``run_live.py --harness tests/live/check.py --plugin src/HideButtons.py --lock-program``
(the 'Stay Probe' program is Character Map, only there to put MO2 in its locked state). Writes the results JSON, closes MO2.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import traceback
from pathlib import Path

import mobase
from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget

CONFIG = json.loads(Path(__file__).with_name("harness_config.json").read_text(encoding="utf-8"))
RESULTS = Path(CONFIG["results"])
PLUGIN = CONFIG.get("plugin_name", "Hide Buttons Plugin")
DEFAULTS = json.loads(CONFIG["defaults"]) if "defaults" in CONFIG else None  # what this edition should start with
NO_WINDOW = 0x08000000


class Check(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._org = None
        self._out = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": [], "facts": {}}

    def init(self, organizer) -> bool:
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._ready)
        return True

    def name(self): return "Hide Buttons Check"
    def author(self): return "tests"
    def description(self): return "Test-only"
    def version(self): return mobase.VersionInfo(0, 1, 0, mobase.ReleaseType.FINAL)
    def settings(self): return []
    def displayName(self): return "Hide Buttons Check"
    def tooltip(self): return "Test-only"
    def icon(self): return QIcon()
    def display(self): pass

    # ---- plumbing
    def _check(self, name: str, ok: bool, detail="") -> None:
        self._out["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:1500]})

    def _find(self, cls, obj):
        return next((w for w in self._main.findChildren(cls) if w.objectName() == obj), None)

    def _set(self, key, value) -> None:
        self._org.setPluginSetting(PLUGIN, key, value)

    def _unlock_button(self):
        for b in self._main.findChildren(QPushButton):
            if b.text() == "Unlock" and not b.objectName():
                return b
        return None

    def _lock_text(self) -> str:
        return " | ".join(l.text() for l in self._main.findChildren(QLabel) if l.isVisible() and re.search(r"\(\d+\)\s*$", l.text()))

    def _run(self, steps) -> None:
        it = iter(steps)

        def go():
            try:
                delay, fn = next(it)
            except StopIteration:
                return
            QTimer.singleShot(delay, lambda: (self._guard(fn), go()))
        go()

    def _guard(self, fn) -> None:
        try:
            fn()
        except Exception:
            self._check("exception in " + getattr(fn, "__name__", "step"), False, traceback.format_exc())

    # ---- scenario
    def _ready(self, main) -> None:
        self._main = main
        self._shots = RESULTS.parent
        self._popup_actions: list = []
        self._run([
            (2500, self._check_static),
            (200, self._open_downloads_menu_hidden),
            (900, self._grab_menu),
            (300, self._turn_bulk_delete_off), (200, self._open_downloads_menu_control), (900, self._grab_menu),
            (300, self._start_lock),
            (4000, self._lock_game_only_not_game),
            (1200, self._lock_extra_game_exe),
            (1200, self._lock_game_only_off_then_unlock_off),
            (1200, self._lock_back_on),
            (1200, self._end_lock),
            (3000, self._finish),
        ])

    def _check_static(self) -> None:
        if DEFAULTS is not None:  # the edition's starting options, before this test changes any
            actual = {k: self._org.pluginSetting(PLUGIN, k) for k in DEFAULTS}
            self._check(f"{PLUGIN}: starting options are as designed", actual == DEFAULTS, actual)
        self._set("hide_bulk_delete", True)  # the checks below exercise every feature, whatever the edition starts with
        self._set("hide_unlock", True)
        self._set("unlock_game_only", True)
        sort = self._find(QPushButton, "sortButton")
        self._check("Sort button hidden at start", sort is not None and not sort.isVisible(), sort and sort.isVisible())
        action = self._main.findChild(QAction, "actionChange_Game")
        self._check("Instance Manager action found", action is not None)
        if action is not None:
            action.setVisible(True)  # as if MO2 re-showed it: the plugin must put it away again
            QTimer.singleShot(300, lambda: self._check("Instance Manager re-hidden after MO2 shows it", not action.isVisible()))
        self._out["facts"]["game_binary"] = self._org.managedGame().binaryName()
        se = self._org.gameFeatures().gameFeature(mobase.ScriptExtender)  # the call the plugin uses for SKSE/F4SE
        self._check("Script extender API works", se is not None and bool(se.binaryName()), se and se.binaryName())

    def _open_downloads_menu_hidden(self) -> None:
        self._popup_label = "bulk delete hidden"
        view = self._find(QWidget, "downloadView")
        pos = QPoint(5, view.height() - 5)
        QTimer.singleShot(500, self._record_popup)
        view.customContextMenuRequested.emit(pos)

    def _turn_bulk_delete_off(self) -> None:
        self._set("hide_bulk_delete", False)

    def _open_downloads_menu_control(self) -> None:
        self._popup_label = "bulk delete shown when option off"
        view = self._find(QWidget, "downloadView")
        pos = QPoint(5, view.height() - 5)
        QTimer.singleShot(500, self._record_popup)
        view.customContextMenuRequested.emit(pos)

    def _record_popup(self) -> None:
        pop = QApplication.activePopupWidget()
        if isinstance(pop, QMenu):
            visible = [a.text() for a in pop.actions() if a.isVisible()]
            self._popup_actions = visible
            pop.grab().save(str(self._shots / (self._popup_label.replace(" ", "_") + ".png")))
            self._out["facts"][self._popup_label] = visible
            pop.close()
        else:
            self._popup_actions = None

    def _grab_menu(self) -> None:
        acts = self._popup_actions
        if self._popup_label == "bulk delete hidden":
            self._check("Downloads menu: no bulk Delete entries, Hide entries kept",
                        acts is not None and not any(a.startswith("Delete") for a in acts) and any(a.startswith("Hide") for a in acts), acts)
            # QMenu collapses the separator it is left with visually (checked in the saved screenshot), not in action.isVisible()
        else:
            self._check("Downloads menu: bulk Delete entries come back when the option is off",
                        acts is not None and sum(a.startswith("Delete") for a in acts) == 3, acts)
        self._set("hide_bulk_delete", True)

    def _start_lock(self) -> None:
        self._set("hide_unlock", True)
        self._set("unlock_game_only", True)
        self._set("extra_game_exes", "")
        box = self._find(QWidget, "executablesListBox")
        box.setCurrentIndex(box.findText("Stay Probe"))
        start = self._find(QWidget, "startButton")
        QTimer.singleShot(100, start.click)  # blocks while locked; the timers above keep running

    def _lock_game_only_not_game(self) -> None:
        b = self._unlock_button()
        self._out["facts"]["lock_label"] = self._lock_text()
        self._out["facts"]["watched"] = b is not None and b.property("hide_buttons_watched")
        self._out["facts"]["btn_parent"] = b is not None and (type(b.parentWidget()).__name__, b.parentWidget().isVisible(), [l.text() for l in b.parentWidget().findChildren(QLabel)], len(b.parentWidget().findChildren(QPushButton)))
        self._check("Locked screen reached", b is not None, self._lock_text())
        self._check("Game-only: Unlock stays for a non-game program (charmap.exe)", b is not None and b.isVisible())
        self._set("extra_game_exes", "charmap.exe")

    def _lock_extra_game_exe(self) -> None:
        b = self._unlock_button()
        self._check("Game-only: Unlock hidden once the program counts as the game", b is not None and not b.isVisible())
        self._set("unlock_game_only", False)
        self._set("extra_game_exes", "")

    def _lock_game_only_off_then_unlock_off(self) -> None:
        b = self._unlock_button()
        self._check("Always mode: Unlock hidden for any program", b is not None and not b.isVisible())
        self._set("hide_unlock", False)

    def _lock_back_on(self) -> None:
        b = self._unlock_button()
        self._check("Option off: Unlock visible again", b is not None and b.isVisible())

    def _end_lock(self) -> None:
        m = re.search(r"charmap\.exe \((\d+)\)", self._lock_text())
        if m:
            subprocess.run(["taskkill", "/PID", m.group(1), "/F"], capture_output=True, creationflags=NO_WINDOW)
        else:
            self._check("could find the program to close", False, self._lock_text())

    def _finish(self) -> None:
        self._out["passed"] = bool(self._out["checks"]) and all(c["ok"] for c in self._out["checks"])
        RESULTS.write_text(json.dumps(self._out, indent=1, default=str), encoding="utf-8")
        QTimer.singleShot(1000, self._main.close)


def createPlugin():
    return Check()
