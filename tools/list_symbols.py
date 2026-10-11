"""工具：list_symbols —— 提取文件结构骨架（类、函数、方法、常量）"""

import ast
import re

from tools import register, resolve_workspace_path
from tools.read_code import _read_text

MAX_SYMBOLS = 200

# 非 Python 语言的"符号"粗提取规则
_PATTERNS = [
    ("class", re.compile(r"^\s*class\s+([A-Za-z_]\w*)")),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)")),
    ("arrow", re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(")),
    ("java_type", re.compile(r"^\s*(?:public|private|protected)?\s*(?:final\s+|abstract\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)")),
    ("struct", re.compile(r"^\s*(?:typedef\s+)?struct\s+([A-Za-z_]\w*)")),
    ("import", re.compile(r"^\s*(?:import|from|#include|use|package)\s+([\w./\-<>]+)")),
]


def _docstring_summary(node) -> str:
    """取 docstring 首行，作为符号的一句话说明。"""
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()[:80]


def _signature(node) -> str:
    """把 ast 参数还原成 Python 文本，例如 (a, b=1, *args, **kwargs) -> int"""
    a = node.args
    parts: list[str] = []

    posonly = getattr(a, "posonlyargs", [])
    for arg in posonly:
        parts.append(arg.arg)
    if posonly:
        parts.append("/")

    for arg in a.args:
        parts.append(arg.arg)

    if a.vararg:
        parts.append(f"*{a.vararg.arg}")
    elif a.kwonlyargs:
        parts.append("*")

    for arg in a.kwonlyargs:
        parts.append(arg.arg)

    if a.kwarg:
        parts.append(f"**{a.kwarg.arg}")

    text = ", ".join(parts)
    if node.returns is not None:
        try:
            text += f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({text})"

def _analyze_python(text: str) -> list[str]:
    """用 ast 精确解析 Python 文件。"""
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        # 语法错误不能崩，要报出错误行号让用户/模型知道
        return [f"[语法错误] 无法解析该 Python 文件：第 {exc.lineno} 行 {exc.msg}"]

    rows: list[str] = []

    # 先收集导入，放在最前面，便于模型了解这个文件的依赖
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or "."
            imports.extend(f"{module}.{alias.name}" for alias in node.names)
    if imports:
        rows.append(f"IMPORTS ({len(imports)}): " + ", ".join(sorted(set(imports))[:25]))

    def emit(node, indent: str, kind: str) -> None:
        name = getattr(node, "name", "?")
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start) or start

        if kind == "class":
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    bases.append("?")
            head = f"{indent}class {name}" + (f"({', '.join(bases)})" if bases else "")
        else:
            head = f"{indent}{_signature(node)}"

        doc = _docstring_summary(node)
        if doc:
            head += f"   # {doc}"
        rows.append(f"L{start}-{end}  {head}")

    # 按源码顺序遍历：顶层符号 + 类内方法 + 大写常量
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            emit(node, "", "class")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    emit(child, "    ", "def")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            emit(node, "", "def")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    rows.append(f"L{node.lineno}  CONST {target.id}")

    return rows


def _analyze_generic(text: str) -> list[str]:
    """非 Python 文件用正则粗提取，够用即可（不追求语法精确）。"""
    rows: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # 跳过注释行
        if line.lstrip().startswith(("//", "#", "*", "/*")):
            continue
        for kind, pattern in _PATTERNS:
            match = pattern.match(line)
            if match:
                rows.append(f"L{lineno}  [{kind}] {match.group(1)}")
                break
    return rows


@register(
    {
        "type": "function",
        "function": {
            "name": "list_symbols",
            "description": (
                "提取一个源码文件的结构骨架：类、函数、方法的名称与所在行号区间"
                "（Python 用 ast 精确解析，并还原函数签名与 docstring 摘要）。"
                "解释代码前应先调用本工具建立全局认识，"
                "然后用 read_code 的 start_line/end_line 精读目标符号，这样更省上下文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "源码文件路径，相对于工作目录"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        }
    }
)
def list_symbols(path: str) -> str:
    from config import load_settings

    settings = load_settings()

    try:
        target = resolve_workspace_path(path, settings.workspace)
    except Exception as exc:
        return f"[错误] {exc}"

    if not target.exists():
        return f"[错误] 文件不存在：{path}"
    if target.is_dir():
        return f"[错误] {path} 是目录。list_symbols 只作用于单个文件。"

    try:
        text, _encoding = _read_text(target)
    except OSError as exc:
        return f"[错误] 读取失败：{exc}"

    if target.suffix.lower() in {".py", ".pyi"}:
        rows = _analyze_python(text)
        engine = "Python ast"
    else:
        rows = _analyze_generic(text)
        engine = "正则粗提取"

    if not rows:
        return f"文件 {path} 中未提取到任何符号（可能是纯数据/配置文件）。"

    overflow = ""
    if len(rows) > MAX_SYMBOLS:
        overflow = f"\n...（另有 {len(rows) - MAX_SYMBOLS} 个符号未列出）"
        rows = rows[:MAX_SYMBOLS]

    return (
        f"文件：{path}（解析方式：{engine}）\n"
        f"共 {len(text.splitlines())} 行，提取到 {len(rows)} 个条目\n"
        f"{'-' * 60}\n"
        + "\n".join(rows)
        + overflow
    )