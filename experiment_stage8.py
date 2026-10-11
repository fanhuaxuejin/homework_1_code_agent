"""阶段 8 验证：边界情况。

重点验证两件事：
    1. 模型输出的工具参数 JSON 被截断时，错误信息是否能让模型自我纠正
    2. 空 / 无意义提问是否给出有意义的反馈

运行：
    python experiment_stage8.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.core import CodeExplainAgent
from agent.llm import ToolCallRequest
from config import load_settings
from tools.loader import load_all

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name}  -> {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def new_agent(max_steps: int = 12) -> CodeExplainAgent:
    return CodeExplainAgent(
        load_settings(), max_steps=max_steps, on_event=lambda e: None
    )


def main() -> int:
    load_all()

    # --------------------------------------------------------- 参数 JSON 截断
    section("1. 工具参数 JSON 被截断（模型输出被 max_tokens 切断）")
    agent = new_agent()
    broken = ToolCallRequest(
        id="call_broken_1",
        name="read_code",
        arguments={},
        raw_arguments='{"path": "demo/sample_goo',
    )
    agent._execute_tool_call(broken)
    content = agent.memory.messages[-1]["content"]
    print(f"    回传给模型的内容：\n      {content[:200]}")

    check(
        "错误信息点明是 JSON 解析失败",
        "JSON" in content,
        "模型只会看到「缺参数」，不知道自己 JSON 坏了，没有理由重发",
    )
    check(
        "错误信息要求模型重发",
        "重新" in content or "重发" in content,
        "没有明确指示，模型可能直接放弃",
    )
    check(
        "结果仍以 role=tool 写入历史（配对没断）",
        agent.memory.messages[-1]["role"] == "tool",
        "role 不对会导致下一轮 400",
    )
    check(
        "tool_call_id 正确带上",
        agent.memory.messages[-1].get("tool_call_id") == "call_broken_1",
        "缺 id 会导致 400",
    )

    # --------------------------------------------------------- 参数 JSON 合法
    section("2. 对照：参数合法的调用不应被影响")
    agent2 = new_agent()
    good = ToolCallRequest(
        id="call_good_1",
        name="read_code",
        arguments={"path": "demo/utils.py", "start_line": 1, "end_line": 3},
        raw_arguments='{"path": "demo/utils.py", "start_line": 1, "end_line": 3}',
    )
    agent2._execute_tool_call(good)
    content2 = agent2.memory.messages[-1]["content"]
    check("正常调用能读到文件内容", "文件：demo/utils.py" in content2, content2[:120])
    check("正常调用不含 JSON 错误字样", "不是合法 JSON" not in content2, "误伤了正常调用")

    # --------------------------------------------------------- 工具名不存在
    section("3. 模型幻觉出不存在的工具名")
    agent3 = new_agent()
    ghost = ToolCallRequest(
        id="call_ghost",
        name="read_file_contents",
        arguments={"file": "a.py"},
        raw_arguments='{"file": "a.py"}',
    )
    agent3._execute_tool_call(ghost)
    content3 = agent3.memory.messages[-1]["content"]
    print(f"    回传：{content3[:160]}")
    check("提示工具不存在", "不存在" in content3, content3[:120])
    check("列出可用工具，模型可改用", "可用工具" in content3, "模型不知道能用什么")
    check("列出了正确的工具名", "read_code" in content3, content3[:160])

    print("\n" + "=" * 64)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  · {item}")
    print("=" * 64)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
