"""
Talia Cyberpunk Audio Visualizer - Root Launcher
Delegates to Python Code/mouth_overlay_app.py.
"""
import os
import sys

CODE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Python Code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from main import main

if __name__ == "__main__":
    main()
