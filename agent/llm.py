from dataclasses import dataclass,field
from typing import Any

from openai import OpenAI

from config import Settings

import json

@dataclass
class ToolCallRequest:
    """模型请求调用某个工具。"""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""

    @property
    def parse_error(self) -> str | None:
        """参数 JSON 是否解析失败"""
        if self.arguments:
            return None
        return f"工具参数不是合法 JSON：{self.raw_arguments[:200]!r}"

@dataclass
class ModelReply:
    content: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    assistant_message: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.provider.base_url,
            timeout=settings.timeout,
            max_retries=0,
        )
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.2,
    ) -> ModelReply:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if self.settings.thinking and self.settings.provider.thinking_extra_body:
            kwargs["extra_body"] = dict(self.settings.provider.thinking_extra_body)

        resp = self.client.chat.completions.create(**kwargs)
        self.calls += 1

        choice = resp.choices[0]
        message = choice.message

        usage = resp.usage
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens

        # ---- 解析工具调用
        tool_calls: list[ToolCallRequest] = []
        for call in getattr(message, "tool_calls", None) or []:
            raw_args = call.function.arguments or ""
            try:
                parsed = json.loads(raw_args) if raw_args.strip() else {}
                if not isinstance(parsed, dict):
                    parsed = {}
            except json.JSONDecodeError:
                parsed = {}
            tool_calls.append(
                ToolCallRequest(
                    id=call.id,
                    name=call.function.name,
                    arguments=parsed,
                    raw_arguments=raw_args,
                )
            )

        # ---- 构造"原样"的 assistant 消息，用于回填历史
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.raw_arguments or "{}"},
                }
                for c in tool_calls
            ]

        return ModelReply(
            content=message.content or "",
            tool_calls=tool_calls,
            assistant_message=assistant_message,
            finish_reason=choice.finish_reason or "",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )

    def usage_text(self) -> str:
        return (
            f"调用 {self.calls} 次 | 输入 {self.prompt_tokens} tokens | "
            f"输出 {self.completion_tokens} tokens"
        )