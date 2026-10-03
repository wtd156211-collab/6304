"""迁移表口径校验错误。"""
from __future__ import annotations


class SpecError(Exception):
    """机名 / 行号 / 说明齐备的校验错误，退出码固定为 2。"""

    def __init__(self, machine: str | None, line: int | None, message: str) -> None:
        self.machine = machine
        self.line = line
        self.message = message
        super().__init__(message)

    def format(self) -> str:
        parts = []
        if self.machine is not None:
            parts.append(f"机名={self.machine}")
        if self.line is not None:
            parts.append(f"行号={self.line}")
        parts.append(self.message)
        return "stateaudit: " + " ".join(parts)
