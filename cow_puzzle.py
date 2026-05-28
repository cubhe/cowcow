"""
极限找牛 / LinkedIn Queens 求解器 + 出题器

规则:
  - N×N 网格, N 种颜色, 每格属于一种颜色
  - 每行 / 每列 / 每种颜色 恰好 1 头牛
  - 任意两头牛不能 8-邻接 (含对角)

用法:
  python cow_puzzle.py                 # 默认生成 8x8 并求解
  python cow_puzzle.py 10              # 生成 10x10
  python cow_puzzle.py 10 --seed 7
  python cow_puzzle.py --load grid.txt # 读取自定义盘面求解
                                       # grid.txt: N 行, 每行 N 个 0-9a-z 字符 (颜色编号)

复杂度: 求解 O(N!) 上界, 实际 N≤16 都在毫秒级.
生成: 随机摆牛 -> 随机洪泛染色 -> 多次重试挑解数最少的; 大 N 不保证唯一解.
"""

from __future__ import annotations

import random
import sys
import time
from typing import List, Optional, Tuple

Grid = List[List[int]]          # grid[r][c] = color id  (0..N-1)
Solution = List[Tuple[int, int]]  # placements[row] = (row, col)


# ---------- 求解 ----------

def solve(grid: Grid) -> Optional[Solution]:
    """按颜色回溯, 颜色按其格子数升序处理 (单元格色被迫立即定位)."""
    n = len(grid)
    color_cells: dict[int, list[tuple[int, int]]] = {}
    for r in range(n):
        for c in range(n):
            color_cells.setdefault(grid[r][c], []).append((r, c))
    color_order = sorted(color_cells.keys(), key=lambda k: len(color_cells[k]))

    row_col = [-1] * n
    used_cols = 0

    def bt(idx: int) -> bool:
        nonlocal used_cols
        if idx == n:
            return True
        cells = color_cells[color_order[idx]]
        for r, c in cells:
            if row_col[r] >= 0:
                continue
            bc = 1 << c
            if used_cols & bc:
                continue
            if r > 0 and row_col[r - 1] >= 0 and abs(row_col[r - 1] - c) <= 1:
                continue
            if r < n - 1 and row_col[r + 1] >= 0 and abs(row_col[r + 1] - c) <= 1:
                continue
            row_col[r] = c
            used_cols |= bc
            if bt(idx + 1):
                return True
            row_col[r] = -1
            used_cols ^= bc
        return False

    if bt(0):
        return [(r, row_col[r]) for r in range(n)]
    return None


def count_solutions(grid: Grid, limit: int = 2) -> int:
    """数解的个数 (按颜色稀有度回溯, 同 solve)."""
    n = len(grid)
    color_cells: dict[int, list[tuple[int, int]]] = {}
    for r in range(n):
        for c in range(n):
            color_cells.setdefault(grid[r][c], []).append((r, c))
    color_order = sorted(color_cells.keys(), key=lambda k: len(color_cells[k]))

    row_col = [-1] * n
    used_cols = 0
    count = 0

    def bt(idx: int) -> bool:
        nonlocal count, used_cols
        if idx == n:
            count += 1
            return count >= limit
        for r, c in color_cells[color_order[idx]]:
            if row_col[r] >= 0:
                continue
            bc = 1 << c
            if used_cols & bc:
                continue
            if r > 0 and row_col[r - 1] >= 0 and abs(row_col[r - 1] - c) <= 1:
                continue
            if r < n - 1 and row_col[r + 1] >= 0 and abs(row_col[r + 1] - c) <= 1:
                continue
            row_col[r] = c
            used_cols |= bc
            if bt(idx + 1):
                return True
            row_col[r] = -1
            used_cols ^= bc
        return False

    bt(0)
    return count


# ---------- 出题 ----------

def _random_placement(n: int, rng: random.Random) -> Optional[Solution]:
    """随机找一组满足 行/列/8-邻接 的摆放 (颜色后面再定)."""
    placements: Solution = []
    used_cols: set[int] = set()

    def bt(row: int) -> bool:
        if row == n:
            return True
        cols = list(range(n))
        rng.shuffle(cols)
        for col in cols:
            if col in used_cols:
                continue
            if row > 0 and abs(placements[-1][1] - col) <= 1:
                continue
            placements.append((row, col))
            used_cols.add(col)
            if bt(row + 1):
                return True
            placements.pop()
            used_cols.remove(col)
        return False

    return placements if bt(0) else None


def _flood_color(n: int, seeds: Solution, rng: random.Random) -> Grid:
    """以牛为种子, 各色轮流扩 1 格, 得到形状还算紧凑且各色都有 ≥1 格的初始划分."""
    grid: Grid = [[-1] * n for _ in range(n)]
    fronts: List[List[Tuple[int, int]]] = [[] for _ in range(n)]
    for color, (r, c) in enumerate(seeds):
        grid[r][c] = color
        fronts[color].append((r, c))
    remaining = n * n - n
    while remaining > 0:
        order = list(range(n))
        rng.shuffle(order)
        progressed = False
        for color in order:
            if not fronts[color]:
                continue
            idx = rng.randrange(len(fronts[color]))
            r, c = fronts[color][idx]
            neigh = [(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))]
            rng.shuffle(neigh)
            grew = False
            for nr, nc in neigh:
                if 0 <= nr < n and 0 <= nc < n and grid[nr][nc] == -1:
                    grid[nr][nc] = color
                    fronts[color].append((nr, nc))
                    remaining -= 1
                    grew = True
                    progressed = True
                    break
            if not grew:
                fronts[color].pop(idx)
        if not progressed:
            # 边角孤立空格: 直接接给某个 4-邻居
            for r in range(n):
                for c in range(n):
                    if grid[r][c] != -1:
                        continue
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < n and 0 <= nc < n and grid[nr][nc] != -1:
                            grid[r][c] = grid[nr][nc]
                            remaining -= 1
                            break
            break
    return grid


def generate(n: int, seed: Optional[int] = None,
             max_tries: int = 300, want_unique: bool = True) -> Tuple[Grid, Solution, int]:
    """随机生成 N×N 谜题. 多次尝试挑解数最少的; 返回 (grid, sol, n_solutions).

    N 大时唯一解很难得 -- 把 want_unique 设 False 直接拿第一个能解的盘.
    """
    rng = random.Random(seed)
    best: Optional[Tuple[Grid, Solution, int]] = None
    for _ in range(max_tries):
        sol = _random_placement(n, rng)
        if sol is None:
            continue
        grid = _flood_color(n, sol, rng)
        c = count_solutions(grid, limit=2)
        if c == 0:
            continue  # 理论上不会发生 (sol 自己就是一个解)
        if c == 1:
            return grid, sol, 1
        if not want_unique:
            return grid, sol, c
        # 记录"解数已知至少为 2 但不知具体多少"的候选
        if best is None:
            best = (grid, sol, c)
    assert best is not None
    return best


# ---------- 输出 ----------

_PALETTE = [
    "\033[48;5;174m", "\033[48;5;108m", "\033[48;5;110m", "\033[48;5;180m",
    "\033[48;5;139m", "\033[48;5;144m", "\033[48;5;167m", "\033[48;5;72m",
    "\033[48;5;179m", "\033[48;5;103m", "\033[48;5;131m", "\033[48;5;151m",
    "\033[48;5;138m", "\033[48;5;152m", "\033[48;5;181m",
]
_RESET = "\033[0m"


def render(grid: Grid, sol: Optional[Solution] = None, color: bool = True) -> str:
    n = len(grid)
    cows = set(sol) if sol else set()
    lines = []
    for r in range(n):
        cells = []
        for c in range(n):
            mark = " C " if (r, c) in cows else f" {grid[r][c]:1x} "
            if color:
                cells.append(f"{_PALETTE[grid[r][c] % len(_PALETTE)]}{mark}{_RESET}")
            else:
                cells.append(mark)
        lines.append("".join(cells))
    return "\n".join(lines)


# ---------- CLI ----------

def load_grid(path: str) -> Grid:
    """读纯文本盘面: N 行, 每行 N 个 0-9 a-z 字符 (颜色编号 0..35)."""
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    n = len(lines)
    grid: Grid = []
    for ln in lines:
        if len(ln) != n:
            raise ValueError(f"行长度 {len(ln)} ≠ {n}; 必须是方阵")
        row = [int(ch, 36) for ch in ln]
        grid.append(row)
    return grid


def main() -> None:
    args = sys.argv[1:]
    seed = None
    load_path = None
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--seed":
            seed = int(args[i + 1]); i += 2
        elif a == "--load":
            load_path = args[i + 1]; i += 2
        elif a in ("-h", "--help"):
            print(__doc__); return
        else:
            pos.append(a); i += 1

    if load_path:
        grid = load_grid(load_path)
        n = len(grid)
        print(f"=== 加载 {n}×{n} 盘面 ({load_path}) ===")
    else:
        n = int(pos[0]) if pos else 8
        t = time.perf_counter()
        grid, _true_sol, n_sols = generate(n, seed=seed)
        t_gen = time.perf_counter() - t
        print(f"=== 生成 {n}×{n}  seed={seed}  耗时 {t_gen*1000:.0f} ms  解数(≤2) = {n_sols} ===")
        if n_sols > 1:
            print("⚠ 未达到唯一解, 当前盘面有多解 (大 N 时常见; 换 seed 多试).")

    t = time.perf_counter()
    found = solve(grid)
    t_solve = time.perf_counter() - t
    if found is None:
        print("× 无解")
        return
    print(f"求解耗时 {t_solve*1000:.2f} ms")
    use_color = sys.stdout.isatty()
    print("\n[盘面]")
    print(render(grid, sol=None, color=use_color))
    print("\n[解]")
    print(render(grid, sol=found, color=use_color))
    print(f"\n牛的位置 (row, col): {found}")


if __name__ == "__main__":
    main()
