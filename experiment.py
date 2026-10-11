"""阶段 7 验证：list_symbols 的结构化提取能力。

重点：Python 走 ast，非 Python 走正则，语法错误不崩。

运行：
    python experiment_stage7.py
"""

import sys
from pathlib import Path

from tools import invoke
from tools.loader import load_all

PROJECT_ROOT = Path(__file__).resolve().parent


def show(title: str, path: str, limit: int = 25) -> None:
    print("=" * 70)
    print(f"{title}  ->  {path}")
    print("=" * 70)
    result = invoke("list_symbols", {"path": path})
    for line in result.splitlines()[:limit]:
        print("  " + line)
    if len(result.splitlines()) > limit:
        print(f"  ...（共 {len(result.splitlines())} 行）")
    print()


def main() -> int:
    load_all()

    # 1. Python 文件 —— 走 ast 分支
    show("1. Python ast 分支（应含签名和 docstring 摘要）", "demo/utils.py")

    # 2. 带类和方法的文件
    show("2. 含 class / property / dataclass 语义", "demo/sample_good.py")

    # 3. 非 Python —— 走正则分支
    show("3. 非 Python 正则分支（JS）", "demo/sample_frontend.js")

    # 4. 你自己的竞赛代码
    show("4. 你的竞赛代码（C++）", "demo/2026 online_1 L.cpp", limit=30)

    # 5. 语法错误文件 —— 必须报行号而不是崩
    print("=" * 70)
    print("5. 语法错误文件（关键边界）")
    print("=" * 70)
    result = invoke("list_symbols", {"path": "demo/sample_syntax_error.py"})
    print("  " + result.replace("\n", "\n  "))
    print()
    if "语法错误" in result:
        print("  ✓ 正确报出语法错误，没有崩溃")
    else:
        print("  ✗ 没有识别出语法错误")

    # 6. 各级错误输入
    print("=" * 70)
    print("6. 错误输入处理")
    print("=" * 70)
    for path in ["demo/不存在.py", "demo", "../../../Windows/win.ini"]:
        r = invoke("list_symbols", {"path": path})
        print(f"  {path:32} -> {r.splitlines()[0][:70]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())