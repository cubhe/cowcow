"""并行修复式生成 N×N 唯一解谜题 (默认 N=12, target 1000), 写入 puzzles_pool.js.

纯随机 flood 在 N=12 良率 < 5e-6, 无法出题. 这里用 cow_puzzle.generate_unique
(flood + 消 alt 解修复), N=12 良率 ~0.7%, 跨核并行几分钟出 1000 题.

复用 bake_graded 的 grade / write_pool / load_existing_pool, 自动与已有 N=9/10/11 合并.

用法:
  py bake_n12.py                      # N=12, 1000 题, 默认 workers
  py bake_n12.py 12 --target 1000 --workers 14
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

from cow_puzzle import generate_unique, count_solutions, score_difficulty
from bake_graded import grade, write_pool, load_existing_pool

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _checkpoint_path(n: int) -> Path:
    return Path(__file__).parent / f"n{n}_checkpoint.json"


def _attempt(arg):
    """单 seed 尝试 (子进程入口). 返回 (seed, rows, nodes) 或 None."""
    seed, n, repair_steps = arg
    res = generate_unique(n, seed=seed, repair_steps=repair_steps)
    if res is None:
        return None
    grid, _sol = res
    if count_solutions(grid, limit=2) != 1:        # 双保险
        return None
    rows = ["".join(DIGITS[v] for v in r) for r in grid]
    nodes = score_difficulty(grid)
    return (seed, rows, nodes)


def _load_checkpoint(n: int):
    cp = _checkpoint_path(n)
    if not cp.exists():
        return [], 0
    data = json.loads(cp.read_text(encoding="utf-8"))
    results = [tuple(r) for r in data.get("results", [])]
    return results, data.get("seed_max", 0)


def _save_checkpoint(n: int, results: list, seed_max: int):
    """写 checkpoint, 并把当前进度 (含已有其他 size) 重新 grade 刷进 pool."""
    cp = _checkpoint_path(n)
    cp.write_text(json.dumps({
        "results": [list(r) for r in results],
        "seed_max": seed_max,
    }, ensure_ascii=False), encoding="utf-8")
    existing = load_existing_pool()
    flat_per_n = {k: v for k, v in existing.items() if k != n}
    flat_per_n[n] = results
    pool = {kk: grade(flat) for kk, flat in flat_per_n.items() if flat}
    write_pool(pool)


def bake_n(n: int, target: int, workers: int, repair_steps: int,
           save_every: int = 50):
    results, seed = _load_checkpoint(n)
    if results:
        print(f">>> 恢复 N={n} checkpoint: {len(results)} 题, seed 从 {seed+1} 继续", flush=True)
    t0 = time.perf_counter()
    print(f"=== N={n}  target={target}  workers={workers}  repair_steps={repair_steps} ===", flush=True)
    last_saved = len(results)
    attempts = 0
    chunksize = 8
    with mp.Pool(workers) as pool:
        while len(results) < target:
            batch = [(seed + i + 1, n, repair_steps)
                     for i in range(workers * chunksize * 4)]
            seed += len(batch)
            for res in pool.imap_unordered(_attempt, batch, chunksize=chunksize):
                attempts += 1
                if res is None:
                    continue
                results.append(res)
                if len(results) % 10 == 0 or len(results) == target:
                    el = time.perf_counter() - t0
                    ns = sorted(r[2] for r in results)
                    p25, p50, p75 = ns[len(ns)//4], ns[len(ns)//2], ns[3*len(ns)//4]
                    yld = len(results) / max(1, attempts) * 100
                    print(f"  [{len(results):4d}/{target}]  {el:5.0f}s  "
                          f"yield={yld:.2f}%  nodes p25/p50/p75={p25}/{p50}/{p75}  "
                          f"{len(results)/el:.2f}题/s", flush=True)
                if len(results) - last_saved >= save_every or len(results) == target:
                    _save_checkpoint(n, results, seed)
                    last_saved = len(results)
                    print(f"  ✓ checkpoint @ {len(results)} 题", flush=True)
                if len(results) >= target:
                    break
    el = time.perf_counter() - t0
    print(f"--- N={n} done: {len(results)} 题 in {el:.0f}s ---", flush=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=12)
    ap.add_argument("--target", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 2))
    ap.add_argument("--repair-steps", type=int, default=500)
    args = ap.parse_args()

    existing = load_existing_pool()
    flat_per_n = {nn: lst for nn, lst in existing.items() if nn != args.n}
    flat_per_n[args.n] = bake_n(args.n, args.target, args.workers, args.repair_steps)

    pool = {nn: grade(flat) for nn, flat in flat_per_n.items()}
    write_pool(pool)
    cp = _checkpoint_path(args.n)
    if cp.exists():
        cp.unlink()
        print(f"  清除 {cp.name}", flush=True)


if __name__ == "__main__":
    main()
