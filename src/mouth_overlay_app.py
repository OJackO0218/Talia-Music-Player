"""
Talia Cyberpunk Audio Visualizer - Application Launcher
Delegates to the modular engine in main.py.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from main import main

if __name__ == "__main__":
    main()
