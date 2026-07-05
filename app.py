"""Development launcher for the Mighty DOOM Admin server.

Run this file directly from the repository root:

    python app.py --db db/local.sqlite3 --password "change-me"

The real application lives in src/mightydoom_admin/server.py so the project
can also be installed as a normal Python package.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python app.py` without requiring an editable pip install first.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mightydoom_admin.server import main


if __name__ == "__main__":
    main()
