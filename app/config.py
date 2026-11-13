"""全局配置：从 .env 读取全部配置项，进程内单例。

所有模块通过 `get_settings()` 访问同一份配置，避免重复解析。
"""
import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- DeepSeek（经 Anthropic SDK 调用）---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_ANTHROPIC_BASE_URL: str = "https://api.deepseek.com/anthropic"
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    # 思考模式模型会先输出 thinking 块，max_tokens 小时导致拿不到 text 块；默认关闭思考
    DEEPSEEK_THINKING: str = "disabled"  # disabled | enabled | ""（不传，用模型默认）

    # --- 存储 ---
    MYSQL_URL: str = "sqlite:///./data/app.db"
    REDIS_URL: str = ""
    CHROMA_PATH: str = "./data/chroma"
    CHROMA_BACKEND: str = "memory"  # 👈 新增这一行：memory | chroma

    # --- 向量 / 重排 ---
    EMB_MODEL: str = "BAAI/bge-small-zh-v1.5"
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    EMBEDDING_BACKEND: str = "hash"  # hash | sentence_transformers
    # HuggingFace 端点：默认直连 huggingface.co；国内可设 https://hf-mirror.com
    HF_ENDPOINT: str = ""
    # 模型已缓存后强制离线：跳过 huggingface 联网校验（hf-mirror 抽风会拖慢启动甚至误降级 hash）
    HF_HUB_OFFLINE: bool = False

    # --- 鉴权 ---
    JWT_SECRET: str = "dev-secret-change-me-in-prod"
    JWT_ALGORITHM: str = "HS256"
    ADMIN_KEY: str = "admin-dev-key"

    # --- 压缩 ---
    WINDOW_TOKENS: int = 32000
    COMPRESS_TRIGGER_RATIO: float = 0.70
    COMPRESS_KEEP_ROUNDS: int = 3
    COMPRESS_LOCK_TTL: int = 60
    # 注入 LLM 上下文的近期消息条数（user+assistant 各算 1 条；压缩触发前的完整窗口）
    CONTEXT_RECENT_MESSAGES: int = 20

    # --- RAG ---
    RRF_K: int = 60
    RERANK_POOL: int = 20
    RERANK_TOP_K: int = 5
    # 重排阈值：jieba 词覆盖度降级用 0.35；语义 CrossEncoder 用原始 logit（RERANK_SEMANTIC_THRESHOLD）
    RERANK_THRESHOLD: float = 0.35
    RERANK_SEMANTIC_THRESHOLD: float = 0.30

    # --- 意图 ---
    HANDOFF_MAX: int = 2
    # 语义后端（sentence_transformers / BGE）阈值：余弦高，需高阈值
    EMB_ABS_THRESHOLD: float = 0.75
    EMB_MARGIN: float = 0.08
    # 哈希后端阈值：hash 向量余弦上限约 0.5，需更低阈值（由 effective_backend 自动选择）
    EMB_HASH_ABS_THRESHOLD: float = 0.35
    EMB_HASH_MARGIN: float = 0.05
    PROFILE_TTL: int = 3600

    # --- ReAct 回路 ---
    REACT_MAX_STEPS: int = 4  # 单轮最多工具调用步数

    # --- 启动 ---
    SEED_DEMO_DATA: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def apply_hf_offline() -> None:
    """模型已缓存时强制离线，跳过 huggingface 联网校验。

    必须在 `import sentence_transformers` 之前调用（env 才会被 huggingface_hub 读到）。
    """
    if get_settings().HF_HUB_OFFLINE:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
