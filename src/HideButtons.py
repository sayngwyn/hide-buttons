"""Hide Buttons: hides chosen buttons in Mod Organizer 2 so a modlist (or you) can't click them by accident.

One plugin, with every option in MO2's Settings > Plugins:
  * the Instance Manager button ("Manage Instances")
  * the plugin Sort (LOOT) button
  * the Unlock button on the "locked while a program runs" screen, optionally only while the game or its script extender runs
  * the bulk "Delete ... Downloads" entries of the Downloads right-click menu

Nothing is polled. MO2's own widgets are found once when its window is ready by their internal names, and later
windows (the lock screen, the Downloads menu) are caught when they appear.
"""

from __future__ import annotations

import os
import re
import traceback

import mobase
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer, qWarning
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMenu, QPushButton

# ---- edition: scripts/build_editions.py rewrites exactly this block to make the other two editions
NAME = "Hide Buttons Plugin"  # MO2 keys the saved settings on this: never rename it
BLURB = "Hides the Manage Instances and Sort buttons."
DEFAULTS = {"hide_instance_manager": True, "hide_sort": True, "hide_unlock": False, "unlock_game_only": True,
            "hide_bulk_delete": False}
# ---- end edition

SORT_BUTTON = "sortButton"  # objectNames MO2 gives these widgets
INSTANCE_ACTION = "actionChange_Game"
LOCK_PROCESS_LINE = re.compile(r"^(?P<exe>.+?)\s*\(\d+\)\s*$", re.MULTILINE)  # the lock screen's "Skyrim.exe (1234)" line(s)
BULK_DELETES = ("Delete Installed Downloads...", "Delete Uninstalled Downloads...", "Delete All Downloads...")
DOWNLOAD_CONTEXTS = ("DownloadListView", "DownloadList", "DownloadsTab", "DownloadManager")  # where MO2 translates its menu


def _plain(text: str) -> str:
    """A menu label without its shortcut ampersand, trailing dots and case, for comparing."""
    return text.replace("&", "").strip().rstrip(".").strip().lower()


def _bulk_delete_labels() -> set[str]:
    """The three bulk-delete labels in English and in MO2's current language."""
    out = set()
    for source in BULK_DELETES:
        out.add(_plain(source))
        for context in DOWNLOAD_CONTEXTS:
            out.add(_plain(QCoreApplication.translate(context, source)))
    return out


def _unlock_texts() -> set[str]:
    """MO2's Unlock button text in English and in MO2's current language."""
    return {"unlock", _plain(QCoreApplication.translate("QObject", "Unlock"))}


class _Watcher(QObject):
    """Application-wide event filter: tells the plugin when a button or menu is shown. Never raises into Qt."""

    def __init__(self, plugin: "HideButtonsPlugin"):
        super().__init__()
        self._plugin = plugin

    def eventFilter(self, obj, event) -> bool:
        try:
            if event.type() == QEvent.Type.Show:
                if isinstance(obj, QPushButton):
                    self._plugin.button_shown(obj)
                elif isinstance(obj, QMenu):
                    self._plugin.menu_shown(obj)
        except Exception:
            self._plugin.log(traceback.format_exc())
        return False


class HideButtonsPlugin(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self._org: mobase.IOrganizer  # set by init(); MO2 always calls init() first
        self._watcher = None
        self._main = None

    # ---- IPlugin
    def init(self, organizer) -> bool:
        self._org = organizer
        organizer.onUserInterfaceInitialized(self._ui_ready)
        return True

    def name(self) -> str:
        return NAME

    def author(self) -> str:
        return "sayngwyn"

    def description(self) -> str:
        return BLURB

    def version(self):
        return mobase.VersionInfo(2, 0, 0, mobase.ReleaseType.FINAL)

    def settings(self):
        return [
            mobase.PluginSetting("hide_instance_manager", "Hide the Manage Instances button", DEFAULTS["hide_instance_manager"]),
            mobase.PluginSetting("hide_sort", "Hide the plugin Sort (LOOT) button", DEFAULTS["hide_sort"]),
            mobase.PluginSetting("hide_unlock", "Hide the Unlock button while a program runs through MO2", DEFAULTS["hide_unlock"]),
            mobase.PluginSetting("unlock_game_only",
                                 "Only hide Unlock while the game or its script extender runs (SKSE, F4SE...); "
                                 "other programs such as xEdit keep their Unlock button", DEFAULTS["unlock_game_only"]),
            mobase.PluginSetting("extra_game_exes",
                                 "More program names that count as the game for the option above (comma separated, "
                                 "e.g. Fallout4Launcher.exe)", ""),
            mobase.PluginSetting("hide_bulk_delete",
                                 "Hide Delete Installed/Uninstalled/All Downloads in the Downloads right-click menu", DEFAULTS["hide_bulk_delete"]),
        ]

    # ---- helpers
    def log(self, text: str) -> None:
        qWarning(f"[Hide Buttons] {text}")

    def _on(self, key: str) -> bool:
        try:
            return bool(self._org.pluginSetting(NAME, key))
        except Exception:
            return DEFAULTS[key]

    def _game_exes(self) -> set[str]:
        """Lower-case program names that count as 'the game': the game, its script extender, and the user's extras."""
        names = set()
        try:
            game = self._org.managedGame()
            names.add(os.path.basename(game.binaryName()).lower())
            extender = self._org.gameFeatures().gameFeature(mobase.ScriptExtender)
            if extender is not None:
                names.add(os.path.basename(extender.binaryName()).lower())
        except Exception:
            self.log(traceback.format_exc())
        try:
            extra = str(self._org.pluginSetting(NAME, "extra_game_exes") or "")
            names.update(os.path.basename(n.strip()).lower() for n in extra.split(",") if n.strip())
        except Exception:
            pass
        return names

    # ---- window ready: the widgets that exist from the start
    def _ui_ready(self, main_window: QMainWindow) -> None:
        try:
            self._main = main_window
            self._watcher = _Watcher(self)
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self._watcher)
            action = main_window.findChild(QAction, INSTANCE_ACTION)
            if action is not None:
                self._keep_instance_manager_hidden(action)
                action.changed.connect(lambda: self._keep_instance_manager_hidden(action))
            sort = main_window.findChild(QPushButton, SORT_BUTTON)
            if sort is not None:
                self.button_shown(sort)
        except Exception:
            self.log(traceback.format_exc())

    def _keep_instance_manager_hidden(self, action: QAction) -> None:
        try:
            if self._on("hide_instance_manager") and action.isVisible():
                action.setVisible(False)
        except Exception:
            self.log(traceback.format_exc())

    # ---- called by the watcher
    def button_shown(self, button: QPushButton) -> None:
        if button.objectName() == SORT_BUTTON:
            if self._on("hide_sort"):
                QTimer.singleShot(0, button.hide)
        elif not button.objectName() and _plain(button.text()) in _unlock_texts():
            self._watch_lock_button(button)

    def menu_shown(self, menu: QMenu) -> None:
        if not self._on("hide_bulk_delete"):
            return
        bulk = _bulk_delete_labels()
        hidden = [a for a in menu.actions() if not a.isSeparator() and _plain(a.text()) in bulk]
        for action in hidden:
            action.setVisible(False)  # QMenu itself collapses the separators this leaves leading or doubled
        if hidden:
            menu.adjustSize()

    # ---- the lock screen
    @staticmethod
    def _lock_exes(button: QPushButton) -> list[str]:
        """Lower-case program names on the lock screen this Unlock button belongs to (empty if none shown yet).

        The 'program (pid)' label sits somewhere above the button in the same lock-screen widget, so look at each ancestor.
        """
        container = button.parentWidget()
        while container is not None:
            for label in container.findChildren(QLabel):
                found = [os.path.basename(m.group("exe")).lower() for m in LOCK_PROCESS_LINE.finditer(label.text() or "")]
                if found:
                    return found
            container = container.parentWidget()
        return []

    def _watch_lock_button(self, button: QPushButton) -> None:
        """Decide now and every 0.4 s while this lock screen exists (the program changes when SKSE hands over to the game)."""
        if button.property("hide_buttons_watched"):
            return
        button.setProperty("hide_buttons_watched", True)
        self._apply_lock(button)
        timer = QTimer(button)  # lives and dies with the button
        timer.timeout.connect(lambda: self._apply_lock(button))
        timer.start(400)

    def _apply_lock(self, button: QPushButton) -> None:
        try:
            parent = button.parentWidget()
            if parent is None or not parent.isVisible():
                return
            ours = bool(button.property("hide_buttons_hid"))  # only ever bring back a button this plugin hid
            hide = self._on("hide_unlock")
            if hide and self._on("unlock_game_only"):
                exes = self._lock_exes(button)
                hide = bool(exes) and any(e in self._game_exes() for e in exes)
            if hide and button.isVisible():
                button.setProperty("hide_buttons_hid", True)
                button.setVisible(False)
            elif not hide and ours:
                button.setProperty("hide_buttons_hid", False)
                button.setVisible(True)
        except Exception:
            self.log(traceback.format_exc())


def createPlugin():
    return HideButtonsPlugin()
