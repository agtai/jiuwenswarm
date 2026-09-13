from __future__ import annotations

import sys
from pathlib import Path


HELPER_ROOT = Path(__file__).resolve().parents[1]
if str(HELPER_ROOT) not in sys.path:
    sys.path.insert(0, str(HELPER_ROOT))
