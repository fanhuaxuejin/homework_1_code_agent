"""tools 包：Agent 可调用的工具集合。

新增一个工具只需三步：
    1. 写 handler，关键字参数，返回 str
    2. 写 schema（OpenAI tools 格式），description 要写清"何时用、参数怎么填"
    3. 用 @register 装饰器注册

阶段 3 只做 read_code 一个工具，阶段 7 再补齐其余。
"""

from .registry import (  # noqa: F401
    UnsafePathError,
    all_schemas,
    get,
    invoke,
    register,
    resolve_workspace_path,
)

__all__ = [
    "UnsafePathError",
    "all_schemas",
    "get",
    "invoke",
    "register",
    "resolve_workspace_path",
]
