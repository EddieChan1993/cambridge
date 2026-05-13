"""
py2app build configuration.
Usage:  python setup.py py2app
"""

import os
from setuptools import setup

APP = ["main.py"]

_icon = "icon.icns" if os.path.exists("icon.icns") else None

OPTIONS = {
    "argv_emulation": False,
    **( {"iconfile": _icon} if _icon else {} ),
    "plist": {
        "CFBundleName": "HotDict",
        "CFBundleDisplayName": "HotDict",
        "CFBundleIdentifier": "com.local.hotdict",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "NSHumanReadableCopyright": "",
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
        "NSAccessibilityUsageDescription": "需要辅助功能权限以使用全局快捷键 ⌘⇧F 查词。",
        "NSAppleEventsUsageDescription": "需要自动化权限以读取所选文字。",
    },
    "packages": [
        "requests",
        "bs4",
        "lxml",
        "openpyxl",
        "objc",
        "AppKit",
        "Foundation",
        "Quartz",
    ],
    "includes": [
        "main",
        "app_delegate",
        "main_window",
        "float_panel",
        "word_display",
        "scraper",
        "data_manager",
        "hotkey_monitor",
        "settings",
        "settings_window",
        "utils",
    ],
    "excludes": ["tkinter", "PyQt5", "PyQt6", "wx", "playwright"],
    "semi_standalone": False,
    "site_packages": True,
}

setup(
    app=APP,
    name="HotDict",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
