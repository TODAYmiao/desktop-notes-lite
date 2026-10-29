"""让 tests/ 直接 `python -m unittest` 就能跑：把仓库根与 .pylibs 加进 sys.path。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for candidate in (REPO_ROOT, REPO_ROOT / ".pylibs"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

# 测试期间不要碰用户真实数据
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
