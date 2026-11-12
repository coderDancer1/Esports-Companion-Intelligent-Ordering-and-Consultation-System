"""HTTP 接口测试（UTF-8 安全，避免 curl 在 Windows 下的编码问题）。"""
import json
import urllib.parse

import requests

BASE = "http://127.0.0.1:8000"
TOK = "demo_u_1001"
H = {"Authorization": f"Bearer {TOK}"}


def show(title, r):
    print(f"\n=== {title} === [{r.status_code}]")
    try:
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(r.text)


show("GET /healthz", requests.get(f"{BASE}/api/v1/healthz", headers=H))
show("GET /playmates/search (valorant 钻石)",
     requests.get(f"{BASE}/api/v1/playmates/search",
                  params={"game": "valorant", "rank_min": "钻石", "rank_max": "钻石"}, headers=H))
show("GET /playmates/p_2001", requests.get(f"{BASE}/api/v1/playmates/p_2001", headers=H))
show("GET /orders", requests.get(f"{BASE}/api/v1/orders", headers=H))
show("POST /chat recommend",
     requests.post(f"{BASE}/api/v1/chat",
                   json={"session_id": "http_1", "message": "帮我推荐一个无畏契约钻石段位的陪玩"}, headers=H))
show("POST /chat order",
     requests.post(f"{BASE}/api/v1/chat",
                   json={"session_id": "http_2", "message": "查询订单 202611080001"}, headers=H))
show("POST /chat knowledge",
     requests.post(f"{BASE}/api/v1/chat",
                   json={"session_id": "http_3", "message": "陪玩怎么收费？"}, headers=H))
show("GET /tickets", requests.get(f"{BASE}/api/v1/tickets", headers=H))
