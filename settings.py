# Copyright © 2026 EddieChan1993. All rights reserved.
# Unauthorized commercial use is strictly prohibited.
"""Persistent settings for Cambridge 查词工具."""

import json
from pathlib import Path

SETTINGS_FILE = Path.home() / ".cambridge_tool" / "settings.json"

# Virtual key-code → display character
KEYCODE_NAMES: dict[int, str] = {
    0: "A",  1: "S",  2: "D",  3: "F",  4: "H",  5: "G",  6: "Z",  7: "X",
    8: "C",  9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R",
   16: "Y", 17: "T", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
   23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
   30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P",
   37: "L", 38: "J", 39: "'", 40: "K", 41: ";", 42: "\\", 43: ",",
   44: "/", 45: "N", 46: "M", 47: ".", 48: "⇥", 49: "Space",
   50: "`", 51: "⌫", 53: "⎋",
   96: "F5", 97: "F6", 98: "F7", 99: "F3", 100: "F8", 101: "F9",
  103: "F11", 109: "F10", 111: "F12", 118: "F4", 120: "F2", 122: "F1",
  123: "←", 124: "→", 125: "↓", 126: "↑",
}

MOD_SYMBOLS = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
MOD_ORDER   = ["ctrl", "alt", "shift", "cmd"]

# (keycode, frozenset(modifiers)) → description of the system shortcut it conflicts with
SYSTEM_CONFLICTS: dict[tuple, str] = {
    (49, frozenset(["cmd"])): "Cmd+Space（Spotlight）",
    (48, frozenset(["cmd"])): "Cmd+Tab（切换应用）",
    (20, frozenset(["cmd", "shift"])): "Cmd+Shift+3（截图）",
    (21, frozenset(["cmd", "shift"])): "Cmd+Shift+4（截图区域）",
    (23, frozenset(["cmd", "shift"])): "Cmd+Shift+5（截图工具栏）",
    (12, frozenset(["cmd"])): "Cmd+Q（退出）",
    (13, frozenset(["cmd"])): "Cmd+W（关闭窗口）",
    (4,  frozenset(["cmd"])): "Cmd+H（隐藏窗口）",
    (46, frozenset(["cmd"])): "Cmd+M（最小化）",
    (8,  frozenset(["cmd"])): "Cmd+C（拷贝）",
    (9,  frozenset(["cmd"])): "Cmd+V（粘贴）",
    (7,  frozenset(["cmd"])): "Cmd+X（剪切）",
    (0,  frozenset(["cmd"])): "Cmd+A（全选）",
    (6,  frozenset(["cmd"])): "Cmd+Z（撤销）",
    (1,  frozenset(["cmd"])): "Cmd+S（存储）",
    (3,  frozenset(["cmd"])): "Cmd+F（查找）",
    (12, frozenset(["cmd", "shift"])): "Cmd+Shift+Q（注销）",
}

DEFAULT_LOOKUP_URL = (
    "https://dictionary.cambridge.org/zhs/"
    "%E8%AF%8D%E5%85%B8/%E8%8B%B1%E8%AF%AD-%E6%B1%89%E8%AF%AD-%E7%AE%80%E4%BD%93"
)

DEFAULTS = {
    "hotkey_keycode": 8,          # C key
    "hotkey_modifiers": ["cmd", "shift"],
    "show_window_keycode": 49,    # Space key
    "show_window_modifiers": ["cmd", "alt"],
    "lookup_base_url": DEFAULT_LOOKUP_URL,
    "sidebar_open_on_start": False,
    "font_size": 14,
    "sync_data_path": "",
}


def hotkey_display(keycode: int, modifiers: list) -> str:
    mods = "".join(MOD_SYMBOLS[m] for m in MOD_ORDER if m in modifiers)
    key  = KEYCODE_NAMES.get(keycode, f"?{keycode}")
    return mods + key


def check_conflict(keycode: int, modifiers: list) -> str:
    """Return description of conflicting system shortcut, or '' if none."""
    return SYSTEM_CONFLICTS.get((keycode, frozenset(modifiers)), "")


class Settings:
    def __init__(self):
        self._data: dict = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    self._data.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            SETTINGS_FILE.parent.mkdir(exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Settings] save error: {e}")

    @property
    def hotkey_keycode(self) -> int:
        return self._data.get("hotkey_keycode", DEFAULTS["hotkey_keycode"])

    @property
    def hotkey_modifiers(self) -> list:
        return self._data.get("hotkey_modifiers", DEFAULTS["hotkey_modifiers"])

    def set_hotkey(self, keycode: int, modifiers: list):
        self._data["hotkey_keycode"]   = keycode
        self._data["hotkey_modifiers"] = list(modifiers)
        self.save()

    def hotkey_display_string(self) -> str:
        return hotkey_display(self.hotkey_keycode, self.hotkey_modifiers)

    @property
    def show_window_keycode(self) -> int:
        return self._data.get("show_window_keycode", DEFAULTS["show_window_keycode"])

    @property
    def show_window_modifiers(self) -> list:
        return self._data.get("show_window_modifiers", DEFAULTS["show_window_modifiers"])

    def set_show_window_hotkey(self, keycode: int, modifiers: list):
        self._data["show_window_keycode"]   = keycode
        self._data["show_window_modifiers"] = list(modifiers)
        self.save()

    def show_window_display_string(self) -> str:
        return hotkey_display(self.show_window_keycode, self.show_window_modifiers)

    @property
    def lookup_base_url(self) -> str:
        return self._data.get("lookup_base_url", DEFAULT_LOOKUP_URL)

    def set_lookup_base_url(self, url: str):
        self._data["lookup_base_url"] = url.strip().rstrip("/")
        self.save()

    @property
    def sidebar_open_on_start(self) -> bool:
        return bool(self._data.get("sidebar_open_on_start", False))

    def set_sidebar_open_on_start(self, value: bool):
        self._data["sidebar_open_on_start"] = value
        self.save()

    @property
    def font_size(self) -> int:
        return int(self._data.get("font_size", DEFAULTS["font_size"]))

    def set_font_size(self, size: int):
        self._data["font_size"] = int(size)
        self.save()

    @property
    def sync_data_path(self) -> str:
        return self._data.get("sync_data_path", "")

    def set_sync_data_path(self, path: str):
        self._data["sync_data_path"] = path.strip()
        self.save()
