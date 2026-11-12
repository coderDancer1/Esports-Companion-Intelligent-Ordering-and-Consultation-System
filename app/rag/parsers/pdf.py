"""PDF 解析：PyMuPDF to_chunks 取 sections；无大纲时 title_path=[] 且 quality=low。"""
from __future__ import annotations

from typing import List, Tuple


def parse(file_bytes: bytes) -> Tuple[List[dict], str]:
    """返回 (sections, doc_parse_quality)。未安装 pymupdf 时返回空并标记 low。"""
    try:
        import fitz  # PyMuPDF
    except Exception:  # noqa: BLE001
        return [], "low"

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        sections: List[dict] = []
        toc = doc.get_toc()  # 大纲 [(level, title, page)]
        if toc:
            # 有目录：按页抽取正文，关联最近标题路径
            for page in doc:
                text = page.get_text().strip()
                if text:
                    sections.append({"title_path": _path_for(toc, page.number + 1),
                                     "level": _level_for(toc, page.number + 1), "text": text})
            quality = "high"
        else:
            for page in doc:
                text = page.get_text().strip()
                if text:
                    sections.append({"title_path": [], "level": 0, "text": text})
            quality = "low"
        doc.close()
        return sections, quality
    except Exception:  # noqa: BLE001
        return [], "low"


def _path_for(toc, page) -> List[str]:
    path: List[str] = []
    for level, title, pg in toc:
        if pg > page:
            break
        while path and len(path) >= level:
            path.pop()
        path.append(title)
    return path


def _level_for(toc, page) -> int:
    level = 0
    for lv, _t, pg in toc:
        if pg > page:
            break
        level = lv
    return level
