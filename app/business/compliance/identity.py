"""实名认证：对接第三方核验通道（此处为可替换的 mock 实现）。"""
from __future__ import annotations

from typing import Dict


def verify_realname(name: str, id_number: str) -> Dict:
    """第三方实名核验。真实环境替换为调用鉴权服务。"""
    if not name or not id_number or len(id_number) not in (15, 18):
        return {"verified": False, "reason": "invalid_input"}
    # mock：演示环境一律通过
    return {"verified": True, "reason": "ok"}
