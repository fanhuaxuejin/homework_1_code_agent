from typing import Any

_LOADED = False


def load_all() -> None:
    """导入全部工具模块（幂等）。"""
    global _LOADED
    if _LOADED:
        return

    # 以下导入的副作用就是"把自己注册进工具表"
    from tools import (
        list_dir,
        list_symbols,
        read_code,
        run_python,
        search_code,
        write_report,
    )

    _LOADED = True


def schemas() -> list[dict[str, Any]]:
    """返回所有已注册工具的 schema。"""
    load_all()
    from tools import all_schemas

    return all_schemas()
