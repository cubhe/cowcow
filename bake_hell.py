"""生成"地狱级"题: min_region=2 (零单色块), 注入为 t6 档, 不动已有 t1..t5.

单色块 (size-1 区域) 会"一格即定位"形成强约束 -> 题目变简单. 这里禁掉它,
整盘没有任何免费定位点, 回溯树更宽更深 -> 地狱难度.

用法:
  py bake_hell.py                       # N=11 和 N=12 各 100 题
  py bake_hell.py --sizes 12 --target 100 --workers 14
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import re
import time
from collections import Counter
from pathlib import Path

from cow_puzzle import generate_unique, count_solutions, score_difficulty

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
OUT_PATH = Path(__file__).parent / "puzzles_pool.js"


def _attempt(arg):
    """单 seed 尝试 (子进程). 返回 (seed, rows, nodes) 或 None."""
    seed, n = arg
    res = generate_unique(n, seed=seed, min_region=2)
    if res is None:
        return None
    grid, _sol = res
    if count_solutions(grid, limit=2) != 1:
        return None
    if min(Counter(v for row in grid for v in row).values()) < 2:  # 双保险: 无单色块
        return None
    rows = ["".join(DIGITS[v] for v in r) for r in grid]
    return (seed, rows, score_difficulty(grid))


def bake_hell(n: int, target: int, workers: int):
    t0 = time.perf_counter()
    print(f"=== 地狱级 N={n}  target={target}  workers={workers} ===", flush=True)
    results = []
    seen = set()
    seed = 0
    chunksize = 6
    with mp.Pool(workers) as pool:
        while len(results) < target:
            batch = [(seed + i + 1, n) for i in range(workers * chunksize * 6)]
            seed += len(batch)
            for res in pool.imap_unordered(_attempt, batch, chunksize=chunksize):
                if res is None:
                    continue
                key = tuple(res[1])
                if key in seen:
                    continue
                seen.add(key)
                results.append(res)
                if len(results) % 10 == 0 or len(results) == target:
                    el = time.perf_counter() - t0
                    print(f"  [{len(results):3d}/{target}]  {el:5.0f}s  {len(results)/el:.2f}题/s", flush=True)
                if len(results) >= target:
                    break
    el = time.perf_counter() - t0
    ns = sorted(r[2] for r in results[:target])
    print(f"--- N={n} 地狱级 done: {len(results)} 题 in {el:.0f}s  "
          f"nodes {ns[0]}-{ns[-1]} (median {ns[len(ns)//2]}) ---", flush=True)
    return results[:target]


def inject_t6(pool_raw: dict, n: int, results: list) -> dict:
    """把 hell 结果按难度升序写成 t6, 保留该 size 现有 t1..t5."""
    s = sorted(results, key=lambda r: r[2])
    t6 = [{"seed": r[0], "rows": r[1], "nodes": r[2]} for r in s]
    pool_raw.setdefault(str(n), {})["t6"] = t6
    return pool_raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[11, 12])
    ap.add_argument("--target", type=int, default=100)
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 2))
    args = ap.parse_args()

    text = OUT_PATH.read_text(encoding="utf-8")
    pool_raw = json.loads(re.search(r"PUZZLE_POOL\s*=\s*(\{.*\});", text, re.S).group(1))

    for n in args.sizes:
        res = bake_hell(n, args.target, args.workers)
        pool_raw = inject_t6(pool_raw, n, res)

    body = json.dumps(pool_raw, ensure_ascii=False, indent=2)
    OUT_PATH.write_text(
        f"// Auto-generated — 不要手改 (bake_graded.py / bake_n12.py / bake_hell.py)\n"
        f"window.PUZZLE_POOL = {body};\n",
        encoding="utf-8")
    print(f"\n写入 {OUT_PATH}")
    for n in args.sizes:
        t6 = pool_raw[str(n)]["t6"]
        ns = sorted(p["nodes"] for p in t6)
        print(f"  N={n} t6 (地狱): {len(t6)} 题  nodes {ns[0]}-{ns[-1]}")


if __name__ == "__main__":
    main()
