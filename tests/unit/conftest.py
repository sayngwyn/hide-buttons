"""Headless unit tests: MO2's `mobase` only exists inside MO2, so a tiny stand-in is put in sys.modules first."""

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

mobase = types.ModuleType("mobase")


class _IPlugin:
    def __init__(self):
        pass


class _PluginSetting:
    def __init__(self, key, description, default):
        self.key, self.description, self.default = key, description, default


class _VersionInfo:
    def __init__(self, *parts):
        self.parts = parts


mobase.IPlugin = _IPlugin
mobase.PluginSetting = _PluginSetting
mobase.VersionInfo = _VersionInfo
mobase.ReleaseType = types.SimpleNamespace(FINAL=0)
mobase.ScriptExtender = object
sys.modules["mobase"] = mobase

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
