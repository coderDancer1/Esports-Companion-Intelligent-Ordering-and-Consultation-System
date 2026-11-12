"""Markdown 解析：按 # 层级构建标题路径。"""
from __future__ import annotations

from typing import List, Tuple


def parse(text: str) -> List[dict]:
    sections: List[dict] = []
    stack: List[Tuple[int, str]] = []  # (level, title)
    current: List[str] = []
    current_meta: dict = {"title_path": [], "level": 0}

    def flush() -> None:
        body = "\n".join(current).strip()
        if body:
            sections.append({"title_path": list(current_meta["title_path"]),
                             "level": current_meta["level"], "text": body})
        current.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            # 收缩标题栈
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_meta = {"title_path": [t for _, t in stack], "level": level}
        elif line.strip():
            current.append(line)
    flush()
    if not sections:
        # 无标题时整篇作为一个 section
        sections.append({"title_path": [], "level": 0, "text": text.strip()})
    return sections
