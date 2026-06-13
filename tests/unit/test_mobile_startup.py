"""Mobile app startup import checks."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


class _KivyDummy:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return _KivyDummy()

    def add_widget(self, *args, **kwargs):
        return None

    def bind(self, *args, **kwargs):
        return None

    def setter(self, name):
        return lambda *args, **kwargs: None

    def run(self):
        return None

    def open(self):
        return None

    def dismiss(self):
        return None


class _KivyApp(_KivyDummy):
    @classmethod
    def get_running_app(cls):
        return None


class _KivyClock:
    def schedule_once(self, callback, *args, **kwargs):
        return None


def _property(default=None):
    return default


def _install_kivy_stubs(monkeypatch):
    modules = {
        "kivy": types.ModuleType("kivy"),
        "kivy.app": types.ModuleType("kivy.app"),
        "kivy.animation": types.ModuleType("kivy.animation"),
        "kivy.clock": types.ModuleType("kivy.clock"),
        "kivy.core": types.ModuleType("kivy.core"),
        "kivy.core.audio": types.ModuleType("kivy.core.audio"),
        "kivy.core.text": types.ModuleType("kivy.core.text"),
        "kivy.core.window": types.ModuleType("kivy.core.window"),
        "kivy.graphics": types.ModuleType("kivy.graphics"),
        "kivy.metrics": types.ModuleType("kivy.metrics"),
        "kivy.properties": types.ModuleType("kivy.properties"),
        "kivy.uix": types.ModuleType("kivy.uix"),
        "kivy.uix.boxlayout": types.ModuleType("kivy.uix.boxlayout"),
        "kivy.uix.button": types.ModuleType("kivy.uix.button"),
        "kivy.uix.image": types.ModuleType("kivy.uix.image"),
        "kivy.uix.label": types.ModuleType("kivy.uix.label"),
        "kivy.uix.popup": types.ModuleType("kivy.uix.popup"),
        "kivy.uix.progressbar": types.ModuleType("kivy.uix.progressbar"),
        "kivy.uix.screenmanager": types.ModuleType("kivy.uix.screenmanager"),
        "kivy.uix.scrollview": types.ModuleType("kivy.uix.scrollview"),
        "kivy.uix.spinner": types.ModuleType("kivy.uix.spinner"),
        "kivy.uix.textinput": types.ModuleType("kivy.uix.textinput"),
        "kivy.uix.widget": types.ModuleType("kivy.uix.widget"),
    }
    modules["kivy.app"].App = _KivyApp
    modules["kivy.animation"].Animation = _KivyDummy
    modules["kivy.clock"].Clock = _KivyClock()
    modules["kivy.core.audio"].SoundLoader = _KivyDummy
    modules["kivy.core.text"].LabelBase = _KivyDummy
    modules["kivy.core.window"].Window = _KivyDummy
    modules["kivy.graphics"].Color = _KivyDummy
    modules["kivy.graphics"].Rectangle = _KivyDummy
    modules["kivy.graphics"].RoundedRectangle = _KivyDummy
    modules["kivy.metrics"].dp = lambda value: value
    modules["kivy.properties"].BooleanProperty = _property
    modules["kivy.properties"].NumericProperty = _property
    modules["kivy.properties"].StringProperty = _property
    modules["kivy.uix.boxlayout"].BoxLayout = _KivyDummy
    modules["kivy.uix.button"].Button = _KivyDummy
    modules["kivy.uix.image"].Image = _KivyDummy
    modules["kivy.uix.label"].Label = _KivyDummy
    modules["kivy.uix.popup"].Popup = _KivyDummy
    modules["kivy.uix.progressbar"].ProgressBar = _KivyDummy
    modules["kivy.uix.screenmanager"].Screen = _KivyDummy
    modules["kivy.uix.screenmanager"].ScreenManager = _KivyDummy
    modules["kivy.uix.screenmanager"].SlideTransition = _KivyDummy
    modules["kivy.uix.scrollview"].ScrollView = _KivyDummy
    modules["kivy.uix.spinner"].Spinner = _KivyDummy
    modules["kivy.uix.textinput"].TextInput = _KivyDummy
    modules["kivy.uix.widget"].Widget = _KivyDummy

    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_mobile_entry_imports_with_buildozer_layout(monkeypatch):
    _install_kivy_stubs(monkeypatch)

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.syspath_prepend(str(root / "mobile"))
    monkeypatch.syspath_prepend(str(root / "src"))

    for name in list(sys.modules):
        if name == "main" or name == "mobile.main" or name.startswith(("screens.", "widgets.", "service.")):
            monkeypatch.delitem(sys.modules, name, raising=False)

    module = importlib.import_module("main")

    assert hasattr(module, "XianxiaApp")
