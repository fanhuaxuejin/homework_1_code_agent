"""工具：run_python —— 在受控条件下运行一小段 Python 代码。"""

import os
import subprocess
import sys
import time
from pathlib import Path

from tools import register

MAX_OUTPUT_CHARS = 6_000
_SECRET_ENV_HINTS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _sanitize_env() -> dict[str, str]:
    """构造子进程环境变量，剔除含密钥的项。"""
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(hint in k.upper() for hint in _SECRET_ENV_HINTS)
    }
    env["PYTHONUNBUFFERED"] = "1"        # 便于捕获崩溃前的最后一行输出
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@register(
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "执行一小段 Python 代码并返回 stdout/stderr。"
                "当你需要验证某段代码的真实行为、打印中间结果、确认某函数返回值时使用。"
                "只应提交短小、无副作用的片段。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 源码"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认取配置值，最大 30"},
                },
                "required": ["code"],
                "additionalProperties": False,
            },
        }
    }
)
def run_python(code: str, timeout: int | None = None) -> str:
    from config import load_settings

    settings = load_settings()

    if not code or not code.strip():
        return "[错误] code 为空。请提供要执行的 Python 代码。"

    limit = settings.run_python_timeout if timeout is None else int(timeout)
    limit = max(1, min(limit, 30))

    tmp_dir = settings.workspace / ".agent_tmp"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = tmp_dir.resolve()
    except OSError as exc:
        return f"[错误] 无法创建临时执行目录 {tmp_dir}：{exc}"

    script = tmp_dir / f"snippet_{os.getpid()}_{int(time.time() * 1000) % 100000}.py"
    try:
        script.write_text(code, encoding="utf-8")
    except OSError as exc:
        return f"[错误] 无法写入临时脚本 {script}：{exc}"

    try:
        proc = subprocess.run(
            [sys.executable, "-B", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=limit,
            cwd=str(settings.workspace),
            env=_sanitize_env(),
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        exit_code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = f"执行超时（超过 {limit} 秒）已被强制终止。可能存在死循环或阻塞等待输入。"
        exit_code = -1
        timed_out = True
    except OSError as exc:
        return f"[错误] 无法启动 Python 子进程：{exc}"
    finally:
        # 用完立即删除
        try:
            script.unlink(missing_ok=True)
        except OSError:
            pass

    def clip(text: str) -> str:
        if len(text) <= MAX_OUTPUT_CHARS:
            return text
        return text[:MAX_OUTPUT_CHARS] + f"\n...[输出过长已截断，共 {len(text)} 字符]"

    parts = [f"执行状态：{'超时' if timed_out else '完成'} | 退出码：{exit_code}"]
    parts.append("-" * 60)
    parts.append("stdout:\n" + (clip(stdout) if stdout else "(空)"))
    if stderr:
        parts.append("stderr:\n" + clip(stderr))
    return "\n".join(parts)