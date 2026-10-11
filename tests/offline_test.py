"""离线冒烟测试（阶段 1 起就可用，随阶段推进逐步补充）。

核心学习点：**分层设计让测试变便宜**
    工具层不依赖 LLM，所以可以不联网、不花一分钱就把它们全测一遍。
    如果你的代码做不到这样测，说明耦合太紧了 —— 回去重构。

运行：
    python tests/offline_test.py
"""

from __future__ import annotations

import py_compile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name}  -> {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ============================================================ 骨架完整性
section("骨架完整性（阶段 1 就该通过）")

# 1. 关键文件是否齐备
expected_files = [
    "config.py", "requirements.txt", ".gitignore", ".env.example", ".gitattributes",
    "agent/__init__.py", "agent/core.py", "agent/llm.py", "agent/memory.py", "agent/prompts.py",
    "tools/__init__.py", "tools/registry.py", "tools/loader.py",
    "tools/read_code.py", "tools/list_symbols.py", "tools/list_dir.py",
    "tools/search_code.py", "tools/run_python.py", "tools/write_report.py",
]
missing = [f for f in expected_files if not (PROJECT_ROOT / f).exists()]
check("关键文件齐备", not missing, f"缺失：{missing}")

# 2. 已有的 .py 文件语法必须能编译
#    注意：骨架里有大量 NotImplementedError，那是**运行期**的，
#    这里只检查**语法**，所以 NotImplementedError 不会被判定为失败。
#    同时必须跳过 demo/：那里的 sample_syntax_error.py 是**故意写的语法错误**测试数据，
#    拿它做语法检查必然误报。
syntax_errors: list[str] = []
for path in sorted(PROJECT_ROOT.rglob("*.py")):
    if any(part in {".venv", "venv", "__pycache__", ".deps", "demo"} for part in path.parts):
        continue
    try:
        py_compile.compile(str(path), doraise=True, cfile=None)
    except py_compile.PyCompileError as exc:
        syntax_errors.append(f"{path.relative_to(PROJECT_ROOT)}: {exc.msg}")
check("全部 .py 文件语法正确（已排除 demo/ 的故意错误样例）", not syntax_errors, "; ".join(syntax_errors[:3]))


# ============================================================ 敏感信息防护
section("敏感信息防护")

gitignore = (PROJECT_ROOT / ".gitignore")
if gitignore.exists():
    content = gitignore.read_text(encoding="utf-8")
    check(".gitignore 忽略 .env", any(
        line.strip() == ".env" for line in content.splitlines()
    ), "没有找到独立的 .env 行")

    # 检查是否存在"注释行吞掉规则"的经典错误
    swallowed = [
        line for line in content.splitlines()
        if line.startswith("#") and line.rstrip().endswith(("/", ".env", "*.log"))
    ]
    check(".gitignore 无'注释吞规则'错误", not swallowed, f"可疑行：{swallowed}")

env_example = PROJECT_ROOT / ".env.example"
if env_example.exists():
    text = env_example.read_text(encoding="utf-8")
    # 模板里放真实 Key 是最常见的事故
    import re
    real_key = re.search(r"LLM_API_KEY=sk-[A-Za-z0-9]{20,}", text)
    check(".env.example 里没有真实 Key", real_key is None,
          "模板里出现了疑似真实 Key，必须替换成占位符")


# ============================================================ 阶段 1：配置层
section("阶段 1：配置层（实现 config.py 后应通过）")

try:
    from config import describe, load_settings  # noqa: E402

    try:
        settings = load_settings(workspace=PROJECT_ROOT)
        check("load_settings 可调用", True)
        print(f"     {describe(settings)}")

        check("provider 为 deepseek", settings.provider.name == "deepseek", settings.provider.name)
        check("base_url 已填写", bool(settings.provider.base_url), "base_url 为空，去查官方文档")
        check("模型名已填写", bool(settings.model), "模型名为空")
        check("工作目录为绝对路径", settings.workspace.is_absolute(), str(settings.workspace))

        # 占位符不能被误判为有效 Key
        placeholder = "sk-" + "请替换为你的真实Key"
        if settings.api_key == placeholder:
            check("占位符 Key 未被误判为有效", settings.has_api_key is False, "占位符被当成有效 Key")
        else:
            check("has_api_key 与 api_key 一致",
                  settings.has_api_key == bool(settings.api_key),
                  f"长度={len(settings.api_key)} has={settings.has_api_key}")

        # describe 不能泄露 Key 明文
        desc = describe(settings)
        if settings.api_key and len(settings.api_key) > 10:
            check("describe 不泄露 Key 明文", settings.api_key not in desc, "摘要里出现了完整 Key")
    except NotImplementedError as exc:
        check("load_settings 已实现", False, f"仍是骨架：{exc}")
    except Exception as exc:  # noqa: BLE001
        check("load_settings 可调用", False, f"{type(exc).__name__}: {exc}")

except NotImplementedError as exc:
    check("config.py 可导入", False, f"仍是骨架：{exc}")


# ============================================================ 阶段 3：工具层
section("阶段 3：工具层（实现 registry 与 read_code 后应通过）")

try:
    from tools import invoke  # noqa: E402
    from tools.loader import schemas  # noqa: E402

    try:
        schema_list = schemas()
        names = sorted(s["function"]["name"] for s in schema_list)
        check("工具已装载", len(schema_list) > 0, "一个工具都没注册")
        print(f"     已注册：{names}")

        # 每个 schema 的结构必须合法，否则模型无法调用
        for s in schema_list:
            fn = s["function"]
            ok = (
                s.get("type") == "function"
                and bool(fn.get("name"))
                and bool(fn.get("description"))
                and fn.get("parameters", {}).get("type") == "object"
                and "properties" in fn.get("parameters", {})
            )
            check(f"schema 结构合法: {fn.get('name')}", ok, str(fn)[:100])
    except NotImplementedError as exc:
        check("registry 已实现", False, f"仍是骨架：{exc}")
    except Exception as exc:  # noqa: BLE001
        check("工具装载可调用", False, f"{type(exc).__name__}: {exc}")

except NotImplementedError as exc:
    check("tools/registry.py 可导入", False, f"仍是骨架：{exc}")


# ============================================================ 汇总
print("\n" + "=" * 64)
print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
if FAILED:
    print("\n失败明细：")
    for item in FAILED:
        print(f"  · {item}")
    print("\n提示：骨架阶段的失败是预期的 —— NotImplementedError 表示该阶段还没开始写。")
print("=" * 64)
sys.exit(1 if FAILED else 0)
