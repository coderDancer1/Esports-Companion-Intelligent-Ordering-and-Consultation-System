"""Skills 加载：扫描 SKILL.md 解析 frontmatter 生成目录；load_skill 返回正文+依赖工具。"""
from __future__ import annotations

import os
from typing import Any, Dict, List

_SKILLS_DIR = os.path.dirname(__file__)
_catalog: Dict[str, Dict[str, Any]] = {}
_loaded = False


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end < 0:
        return meta
    block = text[3:end].strip()
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        meta[k.strip()] = v
    return meta


def _load_all() -> None:
    global _loaded
    if _loaded:
        return
    for entry in os.listdir(_SKILLS_DIR):
        path = os.path.join(_SKILLS_DIR, entry)
        if os.path.isdir(path):
            skill_md = os.path.join(path, "SKILL.md")
            if os.path.exists(skill_md):
                with open(skill_md, "r", encoding="utf-8") as f:
                    content = f.read()
                meta = _parse_frontmatter(content)
                name = meta.get("name", entry)
                body = content[content.find("\n---", 3) + 4:] if content.startswith("---") else content
                _catalog[name] = {
                    "name": name,
                    "description": meta.get("description", ""),
                    "triggers": meta.get("triggers", []),
                    "dependent_tools": meta.get("dependent_tools", []),
                    "content": body.strip(),
                }
    _loaded = True


def get_catalog() -> Dict[str, str]:
    _load_all()
    return {name: info["description"] for name, info in _catalog.items()}


def catalog_text() -> str:
    """skill 目录文本（每行 `- name: description`），供 system prompt 拼装。

    目录每轮常驻 system prompt，正文则靠 load_skill 按需加载（渐进披露）。
    """
    catalog = get_catalog()
    lines = [f"- {name}: {desc}" for name, desc in catalog.items()]
    return "\n".join(lines) or "（无）"


def load_skill(name: str) -> Dict[str, Any]:
    _load_all()
    info = _catalog.get(name)
    if not info:
        return {"content": "", "dependent_tools": [], "found": False}
    return {"content": info["content"], "dependent_tools": info["dependent_tools"],
            "description": info["description"], "found": True}
