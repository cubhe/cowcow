"""并行生成 N 题, 按 score_difficulty 分难度桶, 写入 puzzles_pool.js.

用法:
  py bake_graded.py 9 --target 100 --workers 8
  py bake_graded.py --all   # N=9 和 N=10 各 100
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

from cow_puzzle import generate, score_difficulty

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
OUT_PATH = Path(__file__).parent / "puzzles_pool.js"


def _attempt(arg):
    """单 seed 尝试 (子进程入口). 返回 (seed, rows, nodes) 或 None."""
    seed, n, max_tries = arg
    grid, _sol, n_sols = generate(n, seed=seed, want_unique=True, max_tries=max_tries)
    if n_sols != 1:
        return None
    rows = ["".join(DIGITS[v] for v in r) for r in grid]
    nodes = score_difficulty(grid)
    return (seed, rows, nodes)


def _checkpoint_path(n: int) -> Path:
    return Path(__file__).parent / f"n{n}_checkpoint.json"


def _save_checkpoint(n: int, results: list, seed_max: int):
    """写 checkpoint 到磁盘 + 同时刷新 pool (用当前数据 + 现有其他 size 重新 grade)."""
    cp = _checkpoint_path(n)
    cp.write_text(json.dumps({
        "results": [list(r) for r in results],
        "seed_max": seed_max,
    }, ensure_ascii=False), encoding="utf-8")
    # 同步刷一次 pool, 让网页就算 bake 没跑完也能玩到部分 N=10
    existing = load_existing_pool()
    flat_per_n = {k: v for k, v in existing.items() if k != n}
    flat_per_n[n] = results
    pool = {kk: grade(flat) for kk, flat in flat_per_n.items() if flat}
    write_pool(pool)


def _load_checkpoint(n: int):
    cp = _checkpoint_path(n)
    if not cp.exists():
        return [], 0
    data = json.loads(cp.read_text(encoding="utf-8"))
    results = [tuple(r) for r in data.get("results", [])]
    seed_max = data.get("seed_max", 0)
    return results, seed_max


def bake_n(n: int, target: int, workers: int, max_tries: int = 80_000,
           save_every: int = 50):
    results, seed = _load_checkpoint(n)
    if results:
        print(f"\n>>> 恢复 N={n} checkpoint: {len(results)} 题, seed 从 {seed+1} 继续", flush=True)
    t0 = time.perf_counter()
    print(f"\n=== N={n}  target={target}  workers={workers} ===", flush=True)
    last_saved = len(results)
    # 每 worker 一次拿 chunksize 个 seed 连跑 → PyPy JIT 暖透, 摊薄启动开销
    chunksize = 20
    with mp.Pool(workers) as pool:
        while len(results) < target:
            batch_per_worker = chunksize * 4    # 一批 4× chunksize 量, 维持 worker 不空闲
            batch = [(seed + i + 1, n, max_tries) for i in range(workers * batch_per_worker)]
            seed += len(batch)
            for res in pool.imap_unordered(_attempt, batch, chunksize=chunksize):
                if res is None:
                    continue
                results.append(res)
                if len(results) % 5 == 0 or len(results) == target:
                    el = time.perf_counter() - t0
                    last_nodes = sorted(r[2] for r in results)
                    p25, p50, p75 = last_nodes[len(last_nodes)//4], last_nodes[len(last_nodes)//2], last_nodes[3*len(last_nodes)//4]
                    print(f"  [{len(results):3d}/{target}]  {el:5.0f}s  nodes p25/p50/p75 = {p25}/{p50}/{p75}", flush=True)
                if len(results) - last_saved >= save_every or len(results) == target:
                    _save_checkpoint(n, results, seed)
                    last_saved = len(results)
                    print(f"  ✓ checkpoint @ {len(results)} 题 ({_checkpoint_path(n).name})", flush=True)
                if len(results) >= target:
                    break
    el = time.perf_counter() - t0
    print(f"--- N={n} done in {el:.0f}s ---", flush=True)
    # 完成后清掉 checkpoint
    cp = _checkpoint_path(n)
    if cp.exists():
        cp.unlink()
        print(f"  清除 {cp.name}", flush=True)
    return results


TIER_KEYS = ["t1", "t2", "t3", "t4", "t5"]
# 倾斜分配: t5 (大师) 缩到最难 10%, 其余前 90% 四等分
TIER_PERCENT = [25, 25, 25, 15, 10]


def grade(results):
    """按 TIER_PERCENT 切桶: t1(入门) → t5(大师)."""
    assert sum(TIER_PERCENT) == 100
    s = sorted(results, key=lambda r: r[2])
    n = len(s)
    cum = 0
    bounds = [0]
    for p in TIER_PERCENT:
        cum += p
        bounds.append(n * cum // 100)
    out = {}
    for i, key in enumerate(TIER_KEYS):
        out[key] = [
            {"seed": r[0], "rows": r[1], "nodes": r[2]}
            for r in s[bounds[i]:bounds[i+1]]
        ]
    return out


def load_existing_pool() -> dict:
    """读已有 pool, 找回带 nodes 的原始 puzzle 数据."""
    if not OUT_PATH.exists():
        return {}
    import re
    text = OUT_PATH.read_text(encoding="utf-8")
    m = re.search(r"PUZZLE_POOL\s*=\s*(\{.*\});", text, flags=re.S)
    if not m:
        return {}
    raw = json.loads(m.group(1))
    # 把每个 size 的所有 tier 扁平回 [(seed, rows, nodes), ...]
    out = {}
    for n_str, tiers in raw.items():
        n = int(n_str)
        flat = []
        if isinstance(tiers, dict):
            for lst in tiers.values():
                for item in lst:
                    if isinstance(item, dict) and "rows" in item and "nodes" in item:
                        flat.append((item.get("seed", 0), item["rows"], item["nodes"]))
        if flat:
            out[n] = flat
    return out


def write_pool(pool: dict[int, dict]):
    body = json.dumps(pool, ensure_ascii=False, indent=2)
    OUT_PATH.write_text(
        f"// Auto-generated by bake_graded.py — 不要手改\n"
        f"window.PUZZLE_POOL = {body};\n",
        encoding="utf-8"
    )
    print(f"\n写入 {OUT_PATH}")
    for n, tiers in pool.items():
        for k, lst in tiers.items():
            if lst:
                ns = sorted(p["nodes"] for p in lst)
                print(f"  N={n} {k:6s}: {len(lst):3d} 题  nodes {ns[0]}-{ns[-1]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, help="size (5..12)")
    ap.add_argument("--target", type=int, default=100)
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 2))
    ap.add_argument("--max-tries", type=int, default=80_000)
    ap.add_argument("--all", action="store_true", help="N=9 和 N=10 各 target")
    ap.add_argument("--regrade-only", action="store_true",
                    help="不生成新题, 仅按当前 5 档逻辑重排已有 pool")
    args = ap.parse_args()

    existing = load_existing_pool()  # {n: [(seed, rows, nodes), ...]}

    if args.regrade_only:
        pool = {n: grade(flat) for n, flat in existing.items()}
        write_pool(pool)
        return

    if args.all:
        sizes = [9, 10]
    elif args.n:
        sizes = [args.n]
    else:
        ap.error("给个 N 或 --all 或 --regrade-only")

    # 起点: 保留 existing 里没要 bake 的 size
    flat_per_n = {n: lst for n, lst in existing.items() if n not in sizes}
    for n in sizes:
        flat_per_n[n] = bake_n(n, args.target, args.workers, args.max_tries)
    pool = {n: grade(flat) for n, flat in flat_per_n.items()}
    write_pool(pool)


if __name__ == "__main__":
    main()
