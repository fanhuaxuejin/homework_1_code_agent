"""工具：read_code —— 读取源码文件（带行号）。"""

from pathlib import Path

from config import load_settings
from tools import register, resolve_workspace_path

MAX_CHARS = 24_000

SUPPORTED_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cc",
    ".cs", ".rb", ".php", ".swift", ".scala", ".sh", ".ps1", ".sql",
    ".html", ".css", ".scss", ".vue", ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt", ".ini", ".cfg",
}


def _read_text(path: Path) -> tuple[str, str]:
    """稳健读取：依次尝试多种编码，返回 (文本, 实际用的编码)。

    现实中的代码仓库经常混着 GBK 编码的中文注释，
    直接 open(encoding="utf-8") 会抛 UnicodeDecodeError。
    """
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


@register(
    {
        "type": "function",
        "function": {
            "name": "read_code",
            "description": (
                "读取一个源码文件的内容，返回带行号的文本。"
                "当你需要查看/解释某个文件时使用。"
                "文件很长时应先不带 start_line/end_line 读取，"
                "或先用 list_symbols 定位目标函数所在行，再分段精读。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，相对于工作目录"},
                    "start_line": {"type": "integer", "description": "起始行号（从 1 开始，含）"},
                    "end_line": {"type": "integer", "description": "结束行号（含）。省略则读到末尾"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        }
    }
)
def read_code(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    settings = load_settings()

    try:
        target = resolve_workspace_path(path, settings.workspace)
    except Exception as exc:
        return f"[错误] {exc}"

    if not target.exists():
        return f"[错误] 文件不存在：{path}（已解析为 {target}）"
    if target.is_dir():
        return f"[错误] {path} 是一个目录，请用 list_dir 查看目录内容。"
    if target.suffix.lower() not in SUPPORTED_SUFFIXES:
        return f"[错误] 不支持的文件类型 {target.suffix!r}。"

    try:
        text, encoding = _read_text(target)
    except OSError as exc:
        return f"[错误] 读取文件失败：{exc}"

    lines = text.splitlines()
    total = len(lines)

    start = max(1, start_line or 1)
    end = min(total, end_line or total)
    if start > total:
        return f"[错误] start_line={start} 超出文件总行数（{total} 行）。"
    if end < start:
        return f"[错误] end_line={end} 小于 start_line={start}。"

    width = len(str(end))
    body = "\n".join(f"{i:>{width}} | {lines[i - 1]}" for i in range(start, end + 1))

    header = (
        f"文件：{path}\n"
        f"编码：{encoding} | 总行数：{total} | 本次显示：{start}-{end}\n"
        f"{'-' * 60}\n"
    )

    truncated = False
    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS]
        truncated = True

    footer = ""
    if truncated:
        footer = (
            f"\n{'-' * 60}\n[提示] 内容过长已截断。请改用 start_line/end_line 分段读取，"
            f"例如 start_line={start}, end_line={start + 200}。"
        )
    elif end < total:
        footer = (
            f"\n{'-' * 60}\n[提示] 还有 {total - end} 行未显示。需要时请继续读取 "
            f"start_line={end + 1}, end_line={min(total, end + 200)}。"
        )

    return header + body + footer