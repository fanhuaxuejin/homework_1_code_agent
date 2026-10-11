"""agent 包：Agent 的大脑部分（LLM 封装、核心循环、记忆、提示词）。

阶段顺序建议：
    阶段 1  llm.py     先能发出一次请求
    阶段 2  prompts.py 设计提示词，并体验"单次问答的天花板"
    阶段 4  llm.py 补重试 + core.py 写循环
    阶段 5  memory.py  上下文记忆
"""
