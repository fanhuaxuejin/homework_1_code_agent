"""工具：write_report —— 把结论落盘为 Markdown。"""

import re
import time

from tools import register, resolve_workspace_path

_SAFE_NAME = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff.-]+")


@register(
    {
        "type": "function",
        "function": {
            "name": "write_report",
            "description": (
                "把分析结论写入 reports/ 目录下的 Markdown 文件。"
                "当用户要求'生成解释文档''输出注释''保存分析结果'时使用。"
                "文件名只需给主名，会自动加 .md 后缀与时间戳。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "文件名（不含路径）"},
                    "content": {"type": "string", "description": "Markdown 格式的完整内容"},
                },
                "required": ["filename", "content"],
                "additionalProperties": False,
            },
        }
    }
)
def write_report(filename: str, content: str) -> str:
    from config import load_settings

    settings = load_settings()

    if not content or not content.strip():
        return "[错误] content 为空，没有可写入的内容。"

    # 去掉路径分隔符等危险字符
    stem = _SAFE_NAME.sub("_", filename.strip()).strip("._") or "report"
    if stem.lower().endswith(".md"):
        stem = stem[:-3]

    stamp = time.strftime("%Y%m%d-%H%M%S")
    rel_path = f"reports/{stem}-{stamp}.md"

    try:
        target = resolve_workspace_path(rel_path, settings.workspace)
    except Exception as exc:
        return f"[错误] {exc}"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return f"[错误] 写入失败：{exc}"

    return (
        f"已写入：{rel_path}\n"
        f"绝对路径：{target}\n"
        f"（共 {len(content)} 字符 / {len(content.splitlines())} 行）"
    )