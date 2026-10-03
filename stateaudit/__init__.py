"""状态可达性与死锁检测库。

对外导出：
- load_machines：读取并校验迁移表目录
- analyze：可达性 / SCC / TRAP / CONFLICT / TERMINAL 分析
- Machine / Transition / Analysis / SpecError：核心数据结构
"""
from __future__ import annotations

from .analyze import Analysis, analyze
from .errors import SpecError
from .loader import Machine, Transition, load_machines

__version__ = "1.0.0"

__all__ = [
    "Analysis",
    "Machine",
    "SpecError",
    "Transition",
    "analyze",
    "load_machines",
]
