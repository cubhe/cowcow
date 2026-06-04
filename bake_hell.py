"""生成"地狱级"题: min_region=2 (零单色块) + 难度下限, 注入为 t6 档, 不动 t1..t5.

单色块 (size-1 区域) 会"一格即定位"形成强约束 -> 题目变简单. 这里禁掉它,
并且只保留 score_difficulty(回溯节点数) >= --min-nodes 的硬题.

带断点续跑 (n{N}_hell_checkpoint.json) + 边跑边刷 pool, 跑十几小时也安全.

用法:
  py bake_hell.py --sizes 11 12 --target 1000 --min-nodes 5000 --workers 14
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
    """单 seed 尝试 (子进程). 返回 (seed, rows, nodes) 或 None.
    只接受: 唯一解 + 零单色块 + nodes >= min_nodes."""
    seed, n, min_nodes = arg
    res = generate_unique(n, seed=seed, min_region=2)
    if res is None:
        return None
    grid, _sol = res
    if count_solutions(grid, limit=2) != 1:
        return None
    if min(Counter(v for row in grid for v in row).values()) < 2:
        return None
    nodes = score_difficulty(grid)
    if nodes < min_nodes:
        return None
    rows = ["".join(DIGITS[v] for v in r) for r in grid]
    return (seed, rows, nodes)


def _cp_path(n: int) -> Path:
    return Path(__file__).parent / f"n{n}_hell_checkpoint.json"


def _load_cp(n: int):
    cp = _cp_path(n)
    if not cp.exists():
        return [], set(), 0
    d = json.loads(cp.read_text(encoding="utf-8"))
    results = [tuple(r) for r in d.get("results", [])]
    seen = {tuple(r[1]) for r in results}
    return results, seen, d.get("seed_max", 0)


def _read_pool() -> dict:
    text = OUT_PATH.read_text(encoding="utf-8")
    return json.loads(re.search(r"PUZZLE_POOL\s*=\s*(\{.*\});", text, re.S).group(1))


def _write_pool(pool_raw: dict):
    body = json.dumps(pool_raw, ensure_ascii=False, indent=2)
    OUT_PATH.write_text(
        f"// Auto-generated — 不要手改 (bake_graded.py / bake_n12.py / bake_hell.py)\n"
        f"window.PUZZLE_POOL = {body};\n",
        encoding="utf-8")


def inject_t6(pool_raw: dict, n: int, results: list) -> dict:
    """把 hell 结果按难度升序写成 t6, 保留该 size 现有 t1..t5."""
    s = sorted(results, key=lambda r: r[2])
    pool_raw.setdefault(str(n), {})["t6"] = [
        {"seed": r[0], "rows": r[1], "nodes": r[2]} for r in s]
    return pool_raw


def _save(n: int, results: list, seed: int):
    _cp_path(n).write_text(json.dumps(
        {"results": [list(r) for r in results], "seed_max": seed},
        ensure_ascii=False), encoding="utf-8")
    pool = _read_pool()
    inject_t6(pool, n, results)
    _write_pool(pool)


def bake_hell(n: int, target: int, min_nodes: int, workers: int, save_every: int = 25):
    results, seen, seed = _load_cp(n)
    if results:
        print(f">>> 恢复 N={n} 地狱 checkpoint: {len(results)} 题, seed 从 {seed+1} 继续", flush=True)
    t0 = time.perf_counter()
    print(f"=== 地狱级 N={n}  target={target}  min_nodes={min_nodes}  workers={workers} ===", flush=True)
    last_saved = len(results)
    attempts = 0
    chunksize = 6
    with mp.Pool(workers) as pool:
        while len(results) < target:
            batch = [(seed + i + 1, n, min_nodes) for i in range(workers * chunksize * 8)]
            seed += len(batch)
            for res in pool.imap_unordered(_attempt, batch, chunksize=chunksize):
                attempts += 1
                if res is None:
                    continue
                key = tuple(res[1])
                if key in seen:
                    continue
                seen.add(key)
                results.append(res)
                if len(results) % 5 == 0 or len(results) == target:
                    el = time.perf_counter() - t0
                    ns = sorted(r[2] for r in results)
                    print(f"  [{len(results):4d}/{target}]  {el:6.0f}s  "
                          f"{len(results)/el:.3f}题/s  nodes med={ns[len(ns)//2]} max={ns[-1]}", flush=True)
                if len(results) - last_saved >= save_every or len(results) == target:
                    _save(n, results, seed)
                    last_saved = len(results)
                    print(f"  ✓ checkpoint @ {len(results)} 题", flush=True)
                if len(results) >= target:
                    break
    el = time.perf_counter() - t0
    ns = sorted(r[2] for r in results[:target])
    print(f"--- N={n} 地狱级 done: {len(results)} 题 in {el:.0f}s  "
          f"nodes {ns[0]}-{ns[-1]} (median {ns[len(ns)//2]}) ---", flush=True)
    _save(n, results[:target], seed)
    cp = _cp_path(n)
    if cp.exists():
        cp.unlink()
    return results[:target]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[11, 12])
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--min-nodes", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 2))
    args = ap.parse_args()

    for n in args.sizes:
        bake_hell(n, args.target, args.min_nodes, args.workers)

    pool = _read_pool()
    print(f"\n最终 {OUT_PATH}")
    for n in args.sizes:
        t6 = pool[str(n)]["t6"]
        ns = sorted(p["nodes"] for p in t6)
        print(f"  N={n} t6 (地狱): {len(t6)} 题  nodes {ns[0]}-{ns[-1]}")


if __name__ == "__main__":
    main()
