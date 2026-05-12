#!/usr/bin/env python3
"""
Cambridge — entry point.
Run:  python main.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from app_delegate import AppDelegate


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)

    app.run()


if __name__ == "__main__":
    main()
