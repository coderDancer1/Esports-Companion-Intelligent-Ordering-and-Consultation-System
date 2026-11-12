"""Word 解析：python-docx 读 Heading 样式构建标题路径。"""
from __future__ import annotations

from typing import List, Tuple


def parse(file_bytes: bytes) -> Tuple[List[dict], str]:
    try:
        import docx  # python-docx
        from io import BytesIO
    except Exception:  # noqa: BLE001
        return [], "low"

    try:
        document = docx.Document(BytesIO(file_bytes))
        sections: List[dict] = []
        stack: List[Tuple[int, str]] = []
        current: List[str] = []
        current_meta: dict = {"title_path": [], "level": 0}

        def flush() -> None:
            body = "\n".join(current).strip()
            if body:
                sections.append({"title_path": list(current_meta["title_path"]),
                                 "level": current_meta["level"], "text": body})
            current.clear()

        for para in document.paragraphs:
            style = (para.style.name or "") if para.style else ""
            text = para.text.strip()
            if not text:
                continue
            if style.startswith("Heading") or style == "标题":
                flush()
                try:
                    level = int(style.replace("H    eading", "").strip() or "1")
                except ValueError:
                    level = 1
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text))
                current_meta = {"title_path": [t for _, t in stack], "level": level}
            else:
                current.append(text)
        flush()
        if not sections:
            sections.append({"title_path": [], "level": 0, "text": ""})
        return sections, "high"
    except Exception:  # noqa: BLE001
        return [], "low"
