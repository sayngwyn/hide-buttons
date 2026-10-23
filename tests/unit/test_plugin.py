"""Headless checks of the plugin's logic with real Qt widgets (offscreen). The live MO2 checks are in tests/live."""

import ast

import build_editions
import HideButtons as hb
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QLabel, QMenu, QPushButton, QWidget


class FakeOrganizer:
    def __init__(self, **settings):
        self.settings = settings

    def pluginSetting(self, _name, key):
        return self.settings.get(key, hb.DEFAULTS[key] if key in hb.DEFAULTS else "")


def make_plugin(**settings):
    plugin = hb.HideButtonsPlugin()
    plugin._org = FakeOrganizer(**settings)
    return plugin


def test_plain_ignores_ampersand_dots_and_case():
    assert hb._plain("&Delete Installed Downloads...") == "delete installed downloads"


def test_lock_line_pattern_reads_every_program():
    found = [m.group("exe") for m in hb.LOCK_PROCESS_LINE.finditer("SKSE64_loader.exe (12)\nSkyrimSE.exe (34)")]
    assert found == ["SKSE64_loader.exe", "SkyrimSE.exe"]
    assert hb.LOCK_PROCESS_LINE.search("Mod Organizer is locked while the application is running.") is None


def test_lock_exes_found_from_an_ancestor_of_the_button(qtbot):
    overlay = QWidget()
    qtbot.addWidget(overlay)
    QLabel("Mod Organizer is locked while the application is running.", overlay)
    QLabel("SkyrimSE.exe (4242)", overlay)
    inner = QWidget(overlay)
    button = QPushButton("Unlock", inner)
    assert hb.HideButtonsPlugin._lock_exes(button) == ["skyrimse.exe"]


def test_bulk_delete_entries_hidden_only_when_the_option_is_on(qtbot):
    def menu():
        m = QMenu()
        qtbot.addWidget(m)
        for text in ("Delete Installed Downloads...", "Delete Uninstalled Downloads...", "Delete All Downloads..."):
            m.addAction(text)
        m.addSeparator()
        m.addAction("Hide Installed...")
        return m

    on, off = menu(), menu()
    make_plugin(hide_bulk_delete=True).menu_shown(on)
    make_plugin(hide_bulk_delete=False).menu_shown(off)
    assert [a.text() for a in on.actions() if a.isVisible() and not a.isSeparator()] == ["Hide Installed..."]
    assert sum(a.text().startswith("Delete") and a.isVisible() for a in off.actions()) == 3


def test_instance_manager_action_is_put_away_again(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    action = QAction("Manage Instances", parent)
    action.setVisible(True)
    make_plugin(hide_instance_manager=True)._keep_instance_manager_hidden(action)
    assert not action.isVisible()


def test_editions_differ_only_in_name_description_and_starting_options():
    text = hb.__file__ and open(hb.__file__, encoding="utf-8").read()
    base_rest = build_editions.BLOCK.sub("", text, count=1)
    for stem, (name, blurb, defaults) in build_editions.EDITIONS.items():
        built = build_editions.BLOCK.sub(lambda _: build_editions.block(name, blurb, defaults), text, count=1)
        ast.parse(built)
        assert build_editions.BLOCK.sub("", built, count=1) == base_rest, stem
        assert f'NAME = "{name}"' in built
    names = [n for n, _, _ in build_editions.EDITIONS.values()]
    assert len(set(names)) == 3  # MO2 refuses two plugins with the same name
