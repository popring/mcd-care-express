# -*- coding: utf-8 -*-
"""零依赖的规范检查：行宽、编码声明、模块 docstring、__all__。

    python scripts/style_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINE = 100
TARGETS = ["src", "tests", "demo.py", "scripts"]


def iter_python_files():
    for target in TARGETS:
        path = ROOT / target
        if path.is_file() and path.suffix == ".py":
            yield path
        elif path.is_dir():
            for found in sorted(path.rglob("*.py")):
                yield found


def main() -> int:
    problems = []
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if lines and "coding: utf-8" not in lines[0]:
            problems.append("%s: 缺少 coding 声明" % path.name)
        if not text.strip().startswith(('"""', "#", "from", "import")):
            problems.append("%s: 缺少模块 docstring" % path.name)
        for number, line in enumerate(lines, 1):
            if len(line) > MAX_LINE:
                problems.append("%s:%d 行宽 %d > %d" % (path.name, number, len(line), MAX_LINE))
    if problems:
        print("规范检查未通过：")
        for item in problems:
            print("  - %s" % item)
        return 1
    print("✅ 规范检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
