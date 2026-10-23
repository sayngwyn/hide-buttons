"""Test-only MO2 plugin: dumps what MO2's window really contains (never shipped).

Use it to re-discover widget names after an MO2 update:
``python -I tests/live/run_live.py --harness tests/live/probe.py --lock-program``. It records every button and toolbar action
(objectName, text, tooltip, visibility), the Downloads right-click menu, and the locked screen (Character Map is started
through MO2 to make it appear), writes ``results/probe.json`` and closes MO2.
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import mobase
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QContextMenuEvent, QIcon
from PyQt6.QtWidgets import QAbstractButton, QApplication, QDialog, QMenu, QPushButton, QToolButton, QWidget

OUT = Path(json.loads(Path(__file__).with_name("harness_config.json").read_text(encoding="utf-8"))["results"])


def describe(w: QWidget) -> dict:
    return {"cls": type(w).__name__, "obj": w.objectName(), "text": getattr(w, "text", lambda: "")(), "tip": w.toolTip(),
            "visible": w.isVisible(), "hidden_flag": w.isHidden(), "parent": w.parent().objectName() if w.parent() else None}


def pids(image: str) -> set:
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], capture_output=True, creationflags=0x08000000, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"') and '","' in line}


def dump_buttons(root: QWidget) -> list:
    return [describe(b) for b in root.findChildren(QAbstractButton)]


class Probe(mobase.IPluginTool):
    def __init__(self):
        super().__init__()
        self._org = None
        self._out: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S")}

    def init(self, organizer) -> bool:
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._ready)
        return True

    def name(self): return "Hide Buttons Probe"
    def author(self): return "tests"
    def description(self): return "Test-only"
    def version(self): return mobase.VersionInfo(0, 1, 0, mobase.ReleaseType.FINAL)
    def settings(self): return []
    def displayName(self): return "Hide Buttons Probe"
    def tooltip(self): return "Test-only"
    def icon(self): return QIcon()
    def display(self): pass

    def _ready(self, main) -> None:
        self._main = main
        self._out["mo2_version"] = str(self._org.appVersion())
        self._out["game"] = self._org.managedGame().gameName()
        self._out["game_binary"] = self._org.managedGame().binaryName()
        QTimer.singleShot(3000, self._step_main)

    def _step_main(self) -> None:
        try:
            m = self._main
            self._out["main_buttons"] = dump_buttons(m)
            self._out["toolbar_actions"] = [{"obj": a.objectName(), "text": a.text(), "tip": a.toolTip(), "visible": a.isVisible()}
                                           for a in m.findChildren(__import__("PyQt6.QtGui", fromlist=["QAction"]).QAction)
                                           if a.objectName()]
            self._out["menus"] = {mm.objectName(): [a.text() for a in mm.actions()] for mm in m.findChildren(QMenu)}
            self._out["download_views"] = [describe(w) for w in m.findChildren(QWidget) if "ownload" in w.objectName()]
        except Exception:
            self._out["main_error"] = traceback.format_exc()
        QTimer.singleShot(200, self._step_downloads)

    def _step_downloads(self) -> None:
        try:
            v = next(w for w in self._main.findChildren(QWidget) if w.objectName() == "downloadView")
            pos = QPoint(5, v.height() - 5)
            QTimer.singleShot(500, self._grab_popup)
            v.customContextMenuRequested.emit(pos)  # MO2 builds and exec()s its menu in a slot on this signal
        except Exception:
            self._out["downloads_error"] = traceback.format_exc()
            QTimer.singleShot(200, self._step_lock)

    def _grab_popup(self) -> None:
        pop = QApplication.activePopupWidget()
        if pop is not None:
            self._out["downloads_menu"] = [a.text() for a in pop.actions()] if isinstance(pop, QMenu) else type(pop).__name__
            pop.close()
        else:
            self._out["downloads_menu"] = "no popup"
        QTimer.singleShot(300, self._step_lock)

    def _step_lock(self) -> None:
        try:
            box = next(w for w in self._main.findChildren(QWidget) if w.objectName() == "executablesListBox")
            self._out["executables"] = [box.itemText(i) for i in range(box.count())]
            self._prog_before = pids("charmap.exe")
            box.setCurrentIndex(box.findText("Stay Probe"))
            sb = next(w for w in self._main.findChildren(QWidget) if w.objectName() == "startButton")
            self._out["start_button"] = {"enabled": sb.isEnabled(), "visible": sb.isVisible(), "modal": str(QApplication.activeModalWidget())}
            QTimer.singleShot(200, sb.click)  # click() blocks while MO2 is locked, so the checks below must be scheduled first
        except Exception:
            self._out["start_error"] = traceback.format_exc()
        self._polls = []
        self._poll()
        QTimer.singleShot(9000, self._grab_lock)

    def _poll(self) -> None:
        from PyQt6.QtWidgets import QLabel
        self._polls.append({"program": sorted(pids("charmap.exe") - getattr(self, "_prog_before", set())),
                            "tops": [(type(w).__name__, w.objectName()) for w in QApplication.topLevelWidgets() if w.isVisible()],
                            "unlockish": [describe(b) for b in self._main.findChildren(QAbstractButton) if b.isVisible() and "nlock" in b.text()]})
        import subprocess
        self._out["polls"] = self._polls
        if len(self._polls) < 8:
            QTimer.singleShot(1000, self._poll)

    def _grab_lock(self) -> None:
        try:
            from PyQt6.QtWidgets import QLabel
            self._out["program_started"] = sorted(pids("charmap.exe") - self._prog_before)
            self._out["current_exe"] = [w.currentText() for w in self._main.findChildren(QWidget) if w.objectName() == "executablesListBox"]
            self._out["lockish"] = [describe(w) for w in self._main.findChildren(QWidget) if w.isVisible() and any(k in type(w).__name__.lower() + w.objectName().lower() for k in ("lock", "overlay", "unlock"))]
            self._out["main_buttons_after_launch"] = [d for d in dump_buttons(self._main) if d["visible"]]
            self._out["labels_after_launch"] = [l.text() for l in self._main.findChildren(QLabel) if l.isVisible() and l.text()]
            self._out["top_levels"] = [{**describe(w), "buttons": dump_buttons(w), "labels": [l.text() for l in w.findChildren(QLabel)]}
                                       for w in QApplication.topLevelWidgets() if w.isVisible() and w is not self._main]
        except Exception:
            self._out["lock_error"] = traceback.format_exc()
        self._finish()

    def _finish(self) -> None:
        import subprocess
        for pid in pids("charmap.exe") - getattr(self, "_prog_before", set()):  # only the one this probe started
            subprocess.run(["taskkill", "/T", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
        OUT.write_text(json.dumps(self._out, indent=1, default=str), encoding="utf-8")
        QTimer.singleShot(1500, self._main.close)


def createPlugin():
    return Probe()
