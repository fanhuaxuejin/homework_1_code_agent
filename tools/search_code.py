"""工具：search_code —— 在代码库中检索关键字/正则。
用途：定位符号定义、查找调用点、追踪变量来源等跨文件问题。
"""

import os
import re
from pathlib import Path

from tools import register, resolve_workspace_path
from tools.read_code import SUPPORTED_SUFFIXES, _read_text

MAX_MATCHES = 60
MAX_CHARS = 20_000
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".idea", ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "reports", ".agent_memory", ".agent_tmp",
}


def _relative_display(file: Path, root: Path) -> str:
    """计算用于展示的相对路径。"""
    try:
        return Path(os.path.relpath(file, root)).as_posix()
    except (ValueError, OSError):
        return file.as_posix()

def _iter_files(root: Path, glob: str) -> list[Path]:
    """收集待检索的文件。排序保证同样输入得到同样输出。"""
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if glob:
            if not path.match(glob):
                continue
        elif path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        # 跳过过大的文件（生成的产物、数据集等）
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        files.append(path)
    return sorted(files)


@register(
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "在工作目录内按正则表达式检索代码，返回 文件:行号 及上下文行。"
                "用于定位符号定义、查找调用点、追踪变量来源等跨文件问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式，如 'def parse_\\w+'"},
                    "glob": {"type": "string", "description": "可选文件过滤通配符，如 '*.py'"},
                    "context_lines": {"type": "integer", "description": "命中点前后上下文行数，默认 2，最大 6"},
                    "max_results": {"type": "integer", "description": "最多返回多少条命中，默认 30"},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        }
    }
)
def search_code(
    pattern: str,
    glob: str | None = None,
    context_lines: int = 2,
    max_results: int = 30,
) -> str:
    from config import load_settings

    settings = load_settings()

    # 正则非法要捕获，不能崩
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"[错误] 正则表达式不合法：{exc}。请改用更简单的模式，或对特殊字符转义。"

    context = max(0, min(int(context_lines or 0), 6))
    limit = max(1, min(int(max_results or 30), MAX_MATCHES))

    root = settings.workspace
    files = _iter_files(root, glob or "")
    if not files:
        return f"[无结果] 在 {root} 下没有找到匹配 glob={glob!r} 的文件。"

    blocks: list[str] = []
    total_hits = 0
    scanned = 0
    truncated = False

    for file in files:
        if total_hits >= limit:
            truncated = True
            break
        scanned += 1
        try:
            text, _ = _read_text(file)
        except OSError:
            continue

        lines = text.splitlines()
        rel = _relative_display(file, root)

        for idx, line in enumerate(lines):
            if not regex.search(line):
                continue
            total_hits += 1
            lo = max(0, idx - context)
            hi = min(len(lines), idx + context + 1)
            snippet = "\n".join(
                f"{'>>' if i == idx else '  '} {i + 1:>4} | {lines[i]}"
                for i in range(lo, hi)
            )
            blocks.append(f"--- {rel}:{idx + 1} ---\n{snippet}")
            if total_hits >= limit:
                truncated = True
                break

    if not blocks:
        return (
            f"[无结果] 在 {scanned} 个文件中未找到匹配 {pattern!r} 的内容。\n"
            f"[提示] 可尝试更短的关键字、检查大小写，或放宽 glob 过滤。"
        )

    body = "\n\n".join(blocks)
    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS]
        truncated = True

    header = (
        f"检索：{pattern!r}"
        + (f" | glob={glob}" if glob else "")
        + f"\n命中 {total_hits} 处，扫描 {scanned} 个文件\n"
        + "-" * 60
        + "\n"
    )
    footer = (
        f"\n{'-' * 60}\n[提示] 结果已被截断，请缩小 pattern 范围或调小 max_results。"
        if truncated
        else ""
    )
    return header + body + footer