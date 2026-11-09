"""Backward-compatible launcher for older systemd units that still point here. """

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent / "app"
os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))

from main import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
