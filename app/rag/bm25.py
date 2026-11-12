"""纯 Python BM25 检索（jieba 分词），等价于 bm25s 的本地索引职责。

官方 bm25s 对 Windows/Python3.9 无 wheel，故内置实现，接口语义一致。
"""
from __future__ import annotations

import math
from typing import List, Tuple

import jieba


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.ids: List[str] = []
        self.tokens: List[List[str]] = []
        self.doc_len: List[int] = []
        self.tfs: List[dict] = []
        self.df: dict = {}
        self.avgdl: float = 0.0
        self.N: int = 0

    def tokenize(self, text: str) -> List[str]:
        return [w.strip() for w in jieba.cut_for_search(text) if w.strip()]

    def index(self, ids: List[str], texts: List[str]) -> None:
        self.ids = list(ids)
        self.tokens = [self.tokenize(t) for t in texts]
        self.doc_len = [len(t) for t in self.tokens]
        self.avgdl = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0
        self.N = len(ids)
        self.df = {}
        self.tfs = []
        for toks in self.tokens:
            tf: dict = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            self.tfs.append(tf)
            for t in set(toks):
                self.df[t] = self.df.get(t, 0) + 1

    def score(self, query: str) -> List[float]:
        qt = self.tokenize(query)
        scores: List[float] = []
        for i in range(self.N):
            s = 0.0
            dl = self.doc_len[i]
            tf = self.tfs[i]
            for t in qt:
                if t not in self.df:
                    continue
                idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                f = tf.get(t, 0)
                if f == 0:
                    continue
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1e-6)))
            scores.append(s)
        return scores

    def search(self, query: str, k: int = 30) -> List[Tuple[str, float]]:
        if self.N == 0:
            return []
        scores = self.score(query)
        order = sorted(range(self.N), key=lambda i: scores[i], reverse=True)[:k]
        return [(self.ids[i], scores[i]) for i in order if scores[i] > 0]
