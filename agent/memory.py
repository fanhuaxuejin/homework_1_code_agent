"""上下文记忆：token 估算、滑窗裁剪、会话落盘。
裁剪规则：
    · 永远保留第 0 条 system prompt
    · 永远保留最近 N 条消息
    · 从最旧处丢弃，且**丢弃边界必须落在 user 消息上**
"""

import json
import time
from pathlib import Path
from typing import Any

CHARS_PER_TOKEN = 2.0

def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """
    粗略估算消息列表占用的 token 数。
    """
    total = 0
    for msg in messages:
        total += 4  # 每条消息的角色/分隔符开销
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        # tool_calls 的 arguments 是很容易被忽略的大头，必须算进去
        for call in msg.get("tool_calls") or []:
            fn = call.get("function", {})
            total += len(str(fn.get("name", ""))) + len(str(fn.get("arguments", "")))
    return int(total / CHARS_PER_TOKEN) + 1


class ConversationMemory:
    """会话记忆：存消息、裁剪历史、统计用量、可选落盘。"""

    def __init__(
        self,
        system_prompt: str,
        *,
        max_context_tokens: int = 120_000,
        keep_recent_messages: int = 24,
        store_dir: Path | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.max_context_tokens = max_context_tokens
        self.keep_recent_messages = keep_recent_messages
        self.store_dir = store_dir
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        self.trim_events = 0

    # ------------------------------------------------------------ 基本操作
    @property
    def turns(self) -> int:
        """用户提问轮数。"""
        return sum(1 for m in self.messages if m.get("role") == "user")

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add(self, message: dict[str, Any]) -> None:
        """追加一条原始消息。"""
        self.messages.append(message)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """追加工具执行结果。"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def clear(self, keep_system: bool = True) -> None:
        """清空会话（保留 system prompt）。"""
        if keep_system:
            self.messages = [{"role": "system", "content": self.system_prompt}]
        else:
            self.messages = []

    def context_tokens(self) -> int:
        return estimate_tokens(self.messages)

    # -------------------------------------------------------------- 裁剪
    def trim(self) -> bool:
        """超出预算时裁剪历史。返回是否发生了裁剪。"""
        if self.context_tokens() <= self.max_context_tokens:
            return False

        head = self.messages[:1]          # system prompt
        body = self.messages[1:]
        if len(body) <= self.keep_recent_messages:
            # 已经只剩余最近消息却还超预算：
            # 说明单轮内容本身过长，由工具层的输出上限负责截断，这里不再强行删
            return False

        # 从头部找裁剪边界：边界必须落在 user 消息上
        cut = len(body) - self.keep_recent_messages
        while cut < len(body) and body[cut].get("role") != "user":
            cut += 1
        if cut >= len(body):
            cut = len(body) - self.keep_recent_messages

        dropped = body[:cut]
        self.messages = head + [
            {
                "role": "system",
                "content": (
                    f"[上下文提示] 为控制长度，已省略本会话最早的 {len(dropped)} 条消息。"
                    "如需要其中的内容，请重新调用工具读取文件。"
                ),
            }
        ] + body[cut:]
        self.trim_events += 1
        return True

    # -------------------------------------------------------------- 摘要
    def summary(self) -> str:
        return (
            f"会话轮数 {self.turns} | 消息数 {len(self.messages)} | "
            f"估算上下文 {self.context_tokens()} tokens"
            + (f" | 已裁剪 {self.trim_events} 次" if self.trim_events else "")
        )

    # ------------------------------------------------------------ 持久化
    def save(self, name: str = "last_session") -> Path | None:
        """把会话长期记忆。store_dir 为 None 时不做任何事。"""
        if self.store_dir is None:
            return None
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / f"{name}.json"
        path.write_text(
            json.dumps(
                {
                    "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "turns": self.turns,
                    "estimated_tokens": self.context_tokens(),
                    "messages": self.messages,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def load(self, name: str = "last_session") -> bool:
        """载入上次会话。"""
        if self.store_dir is None:
            return False
        path = self.store_dir / f"{name}.json"
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        restored = [m for m in payload.get("messages", []) if m.get("role") != "system"]
        if not restored:
            return False
        self.messages = [{"role": "system", "content": self.system_prompt}] + restored
        return True