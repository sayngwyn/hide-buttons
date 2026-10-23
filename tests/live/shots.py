"""Test-only MO2 plugin: saves the screenshots used on the Nexus page (never shipped).

``python -I tests/live/run_live.py --harness tests/live/shots.py --lock-program [--plugin src/HideButtons.py --config after=1]``
Saves ``<results>/<before|after>-main.png`` (MO2's window), ``-menu.png`` (Downloads right-click menu) and ``-lock.png``
(the locked screen) and closes MO2. Run it once without the plugin ("before") and once with it ("after").
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
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget

CONFIG = json.loads(Path(__file__).with_name("harness_config.json").read_text(encoding="utf-8"))
RESULTS = Path(CONFIG["results"])
AFTER = CONFIG.get("after") == "1"
PREFIX = "after" if AFTER else "before"
PROGRAM = CONFIG.get("program", "Stay Probe")  # an MO2 executable by name; the game itself for the real screenshots
LOCK_WAIT = int(CONFIG.get("lock_wait_ms", 4000))
NO_WINDOW = 0x08000000


class Shots(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._org = None
        self._out = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "files": [], "errors": []}

    def init(self, organizer) -> bool:
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._ready)
        return True

    def name(self): return "Hide Buttons Shots"
    def author(self): return "tests"
    def description(self): return "Test-only"
    def version(self): return mobase.VersionInfo(0, 1, 0, mobase.ReleaseType.FINAL)
    def settings(self): return []
    def displayName(self): return "Hide Buttons Shots"
    def tooltip(self): return "Test-only"
    def icon(self): return QIcon()
    def display(self): pass

    def _find(self, obj):
        return next((w for w in self._main.findChildren(QWidget) if w.objectName() == obj), None)

    def _save(self, widget, suffix) -> None:
        path = RESULTS.parent / f"{PREFIX}-{suffix}.png"
        widget.grab().save(str(path))
        self._out["files"].append(path.name)

    def _guard(self, fn) -> None:
        try:
            fn()
        except Exception:
            self._out["errors"].append(traceback.format_exc())

    def _run(self, steps) -> None:
        it = iter(steps)

        def go():
            try:
                delay, fn = next(it)
            except StopIteration:
                return
            QTimer.singleShot(delay, lambda: (self._guard(fn), go()))
        go()

    def _ready(self, main) -> None:
        self._main = main
        screens = QGuiApplication.screens()
        if len(screens) > 1:  # keep it off the main screen
            main.move(screens[1].availableGeometry().topLeft())
        self._run([(2500, self._shot_main), (300, self._open_menu), (900, self._shot_menu), (300, self._start_lock),
                   (LOCK_WAIT, self._shot_lock), (500, self._end_lock), (3000, self._finish)])

    def _shot_main(self) -> None:
        self._save(self._main, "main")

    def _open_menu(self) -> None:
        view = self._find("downloadView")
        pos = QPoint(5, view.height() - 5)
        QTimer.singleShot(500, self._menu_popup)
        view.customContextMenuRequested.emit(pos)

    def _menu_popup(self) -> None:
        pop = QApplication.activePopupWidget()
        if isinstance(pop, QMenu):
            self._save(pop, "menu")
            pop.close()

    def _shot_menu(self) -> None:
        pass

    def _start_lock(self) -> None:
        box = self._find("executablesListBox")
        box.setCurrentIndex(box.findText(PROGRAM))
        start = self._find("startButton")
        QTimer.singleShot(100, start.click)  # blocks while locked; the timers keep running

    def _shot_lock(self) -> None:
        self._save(self._main, "lock")

    def _end_lock(self) -> None:
        text = " | ".join(l.text() for l in self._main.findChildren(QLabel) if l.isVisible())
        m = re.search(r"\b[\w.-]+\.exe \((\d+)\)", text)
        if m:
            subprocess.run(["taskkill", "/PID", m.group(1), "/F", "/T"], capture_output=True, creationflags=NO_WINDOW)
        else:
            self._out["errors"].append("could not find the program to close: " + text)

    def _finish(self) -> None:
        RESULTS.write_text(json.dumps(self._out, indent=1), encoding="utf-8")
        QTimer.singleShot(1000, self._main.close)


def createPlugin():
    return Shots()
