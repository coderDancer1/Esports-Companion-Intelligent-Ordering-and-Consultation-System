"""数据飞轮 CLI：把线上弱信号归集成候选评测样例，落盘待人工审核。

用法：
    PYTHONIOENCODING=utf-8 python evals/flywheel.py            # 打印来源统计 + 写入 _flywheel_candidates.json
    PYTHONIOENCODING=utf-8 python evals/flywheel.py --pretty   # 额外打印候选明细
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pretty", action="store_true", help="额外打印候选明细")
    ap.add_argument("--limit", type=int, default=200, help="每类信号最多取多少条")
    args = ap.parse_args()

    from app.db.mysql import create_all
    from app.flywheel import collect_candidates

    create_all()
    data = collect_candidates()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_flywheel_candidates.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("数据飞轮归集完成 →", out_path)
    print("来源统计（待人工审核后并入评测集 / 补录知识库）：")
    for k, v in data["sources"].items():
        print(f"  {k:<20} {v}")

    if args.pretty:
        for group, items in data["candidates"].items():
            if not items:
                continue
            print(f"\n[{group}] {len(items)} 条")
            for it in items[:30]:
                print("  -", json.dumps(it, ensure_ascii=False))


if __name__ == "__main__":
    main()
