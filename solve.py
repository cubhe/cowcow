"""
极限找牛 - 便捷入口.

工作目录:
  ./puzzles/      — 所有源图 + 解码盘面 + 渲染解图都放这里

用法:
  py -3 solve.py                    # 解 puzzles/ 里最新一张未处理的图
  py -3 solve.py path/to/img.png    # 把图复制进 puzzles/, 命名为下一个 p{N}, 求解
  py -3 solve.py --watch            # 持续监听 puzzles/, 新图进来就解
  py -3 solve.py --watch 3          # 监听间隔 3 秒 (默认 2)

每张图都会:
  1. 若不叫 p{N}.jpg, 重命名为下一个空闲 p{N}.jpg
  2. 写 puzzles/p{N}_grid.txt
  3. 渲染 puzzles/p{N}_solved.png
  4. 打印牛位
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from image_to_grid import (
    find_board_bbox, detect_n, sample_cells, cluster_to_grid,
    grid_to_text, save_grid_image,
)
from cow_puzzle import solve

COWCWO_DIR = Path(__file__).parent
PUZZLES_DIR = COWCWO_DIR / "puzzles"
PUZZLES_DIR.mkdir(exist_ok=True)

IMG_EXTS = {".jpg", ".jpeg", ".png"}
PN_RE = re.compile(r"p(\d+)")


def used_pn() -> set[int]:
    s: set[int] = set()
    for p in PUZZLES_DIR.iterdir():
        if p.suffix.lower() in IMG_EXTS:
            m = PN_RE.fullmatch(p.stem)
            if m:
                s.add(int(m.group(1)))
    return s


def next_pn() -> int:
    s = used_pn()
    return (max(s) + 1) if s else 1


def is_solved(pn: int) -> bool:
    return (PUZZLES_DIR / f"p{pn}_solved.png").exists()


def process(src: Path, pn: int) -> tuple[int, list[tuple[int, int]] | None, float]:
    """复制/重命名 + 解 + 渲染. 返回 (N, sol, ms)."""
    dst_jpg = PUZZLES_DIR / f"p{pn}.jpg"
    grid_txt = PUZZLES_DIR / f"p{pn}_grid.txt"
    sol_png = PUZZLES_DIR / f"p{pn}_solved.png"

    t0 = time.perf_counter()
    if src.resolve() != dst_jpg.resolve():
        # 同目录里就用 rename, 否则 copy
        if src.parent.resolve() == PUZZLES_DIR.resolve():
            src.rename(dst_jpg)
        else:
            shutil.copy2(src, dst_jpg)

    img = np.array(Image.open(dst_jpg).convert("RGB"))
    bbox = find_board_bbox(img)
    n = detect_n(img, bbox)
    colors = sample_cells(img, bbox, n)
    grid = cluster_to_grid(colors, n)
    sol = solve(grid.tolist())
    dt = (time.perf_counter() - t0) * 1000

    grid_txt.write_text(grid_to_text(grid) + "\n", encoding="utf-8")
    if sol:
        save_grid_image(grid, sol, str(sol_png))
    return n, sol, dt


def fmt_sol(sol: list[tuple[int, int]]) -> str:
    return " ".join(f"({r},{c})" for r, c in sol)


def scan_inbox() -> list[Path]:
    """启动时补漏: 只挑已命名 p{N}.jpg 但还没解的. 不动其他随手放的图."""
    out: list[Path] = []
    for p in PUZZLES_DIR.iterdir():
        if p.suffix.lower() != ".jpg":
            continue
        m = PN_RE.fullmatch(p.stem)
        if m and not is_solved(int(m.group(1))):
            out.append(p)
    return out


def is_output_file(p: Path) -> bool:
    s = p.stem
    return (s.endswith("_solved") or s.endswith("_debug")
            or s.endswith("_grid") or s.startswith("grid")
            or s.startswith("debug") or s.startswith("overlay")
            or s.startswith("auto_grid") or s.startswith("real_"))


def handle_one(src: Path) -> None:
    m = PN_RE.fullmatch(src.stem)
    if m and src.suffix.lower() == ".jpg":
        pn = int(m.group(1))
    else:
        pn = next_pn()
    try:
        n, sol, dt = process(src, pn)
        label = f"p{pn}"
        if sol:
            print(f"[{label}] {n}×{n}  {dt:.0f}ms  {fmt_sol(sol)}", flush=True)
        else:
            print(f"[{label}] {n}×{n}  无解 ({dt:.0f}ms)", flush=True)
    except Exception as e:
        print(f"[p{pn}] 失败: {e}", flush=True)


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--watch":
        interval = float(args[1]) if len(args) > 1 else 2.0
        print(f"[watch] 监听 {PUZZLES_DIR}, 间隔 {interval}s. Ctrl-C 退出.", flush=True)
        for src in scan_inbox():
            handle_one(src)
        # 记录启动时所有"非输出"图片为已知, 之后只处理"新出现"或"修改时间变新"的
        baseline: set[str] = set()
        for p in PUZZLES_DIR.iterdir():
            if p.suffix.lower() in IMG_EXTS and not is_output_file(p):
                baseline.add(p.name)
        while True:
            time.sleep(interval)
            for p in PUZZLES_DIR.iterdir():
                if p.suffix.lower() not in IMG_EXTS:
                    continue
                if is_output_file(p):
                    continue
                m = PN_RE.fullmatch(p.stem)
                # 已解过的 p{N} 不再处理
                if m and is_solved(int(m.group(1))):
                    baseline.add(p.name)
                    continue
                # 新文件 -> 处理
                if p.name not in baseline:
                    time.sleep(0.5)  # 等写盘完成
                    handle_one(p)
                    baseline.add(p.name)
        return

    if args:
        src = Path(args[0])
        if not src.exists():
            print(f"找不到 {src}", file=sys.stderr)
            sys.exit(1)
        handle_one(src)
        return

    pending = scan_inbox()
    if not pending:
        print(f"puzzles/ 里没有待解的图. 放一张进去或用 --watch.")
        return
    pending.sort(key=lambda p: p.stat().st_mtime)
    handle_one(pending[-1])


if __name__ == "__main__":
    main()
