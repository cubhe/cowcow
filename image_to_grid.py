"""
把"极限找牛"截图自动转为 cow_puzzle.py 可读的盘面文本.

依赖: Pillow, numpy
用法:
  py -3 image_to_grid.py screenshot.png                  # 自动检测, 输出到 stdout
  py -3 image_to_grid.py screenshot.png -o grid.txt      # 写文件
  py -3 image_to_grid.py screenshot.png --n 12           # 强制 N=12
  py -3 image_to_grid.py screenshot.png --debug debug.png # 输出叠加可视化
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


# ---------------- 工具 ----------------

def saturation_mask(img: np.ndarray, thresh: int = 30) -> np.ndarray:
    """高饱和度像素 = 'cell 颜色像素'. 排除白底/灰底 UI."""
    return (img.max(axis=2).astype(int) - img.min(axis=2).astype(int)) > thresh


def _smooth(arr: np.ndarray, win: int) -> np.ndarray:
    """简单滑动均值平滑."""
    if win <= 1:
        return arr
    k = np.ones(win) / win
    return np.convolve(arr, k, mode="same")


_DS = 4  # 降采样因子, bbox/N 检测都在 1/16 尺寸上做


def find_board_bbox(img: np.ndarray) -> tuple[int, int, int, int]:
    """找盘面 bbox: 降采样 → 平滑密度找峰值 → 向两侧扩到密度跌破阈值."""
    small = img[::_DS, ::_DS]
    mask = saturation_mask(small)
    h, w = mask.shape
    row_dens = _smooth(mask.mean(axis=1).astype(np.float32), max(10, h // 20))
    col_dens = _smooth(mask.mean(axis=0).astype(np.float32), max(10, w // 20))
    thresh = 0.18

    pr = int(row_dens.argmax())
    pc = int(col_dens.argmax())

    top = pr
    while top > 0 and row_dens[top - 1] > thresh:
        top -= 1
    bot = pr
    while bot < h - 1 and row_dens[bot + 1] > thresh:
        bot += 1
    left = pc
    while left > 0 and col_dens[left - 1] > thresh:
        left -= 1
    right = pc
    while right < w - 1 and col_dens[right + 1] > thresh:
        right += 1
    return left * _DS, top * _DS, right * _DS, bot * _DS


def detect_n(img: np.ndarray, bbox: tuple[int, int, int, int]) -> int:
    """数格子: 降采样 bbox 区域沿 Y 求列均值, 自适应阈值切块计数."""
    left, top, right, bot = bbox
    crop = img[top : bot + 1 : _DS, left : right + 1 : _DS]
    mask = saturation_mask(crop).astype(np.float32)
    col_avg = mask.mean(axis=0)
    if col_avg.max() < 0.1:
        return 0
    thr = (col_avg.max() + col_avg.min()) / 2
    in_cell = col_avg > thr
    min_w = max(5, (bot - top) // (40 * _DS))
    runs = 0
    i = 0
    while i < len(in_cell):
        if in_cell[i]:
            j = i
            while j < len(in_cell) and in_cell[j]:
                j += 1
            if j - i >= min_w:
                runs += 1
            i = j
        else:
            i += 1
    return runs


def sample_cells(img: np.ndarray, bbox: tuple[int, int, int, int], n: int) -> np.ndarray:
    """每格在 4 个边缘中点采小 patch 取均值; 跨 patch 取中位数 -> 不受 X/牛 icon 干扰."""
    left, top, right, bot = bbox
    cell_w = (right - left + 1) / n
    cell_h = (bot - top + 1) / n
    colors = np.zeros((n, n, 3), dtype=np.float32)
    patch_r = max(2, int(min(cell_w, cell_h) * 0.08))
    off = int(min(cell_w, cell_h) * 0.35)
    offsets = [(-off, 0), (off, 0), (0, -off), (0, off)]  # N S W E
    H, W = img.shape[:2]
    for r in range(n):
        for c in range(n):
            cx = int(left + (c + 0.5) * cell_w)
            cy = int(top + (r + 0.5) * cell_h)
            samples = []
            for dy, dx in offsets:
                py = np.clip(cy + dy, patch_r, H - patch_r - 1)
                px = np.clip(cx + dx, patch_r, W - patch_r - 1)
                patch = img[py - patch_r : py + patch_r + 1,
                            px - patch_r : px + patch_r + 1].astype(np.float32)
                sat = patch.max(axis=2) - patch.min(axis=2)
                m = sat > 20
                if m.sum() >= 3:
                    samples.append(patch[m].mean(axis=0))
            if samples:
                colors[r, c] = np.median(np.stack(samples), axis=0)
            else:
                colors[r, c] = img[cy, cx].astype(np.float32)
    return colors


def kmeans(points: np.ndarray, k: int, n_iters: int = 30,
           seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """简单 k-means++ 初始化 + Lloyd 迭代."""
    rng = np.random.default_rng(seed)
    n = len(points)
    centroids = [points[rng.integers(n)]]
    for _ in range(k - 1):
        d2 = np.min(
            np.stack([((points - c) ** 2).sum(axis=1) for c in centroids], axis=0),
            axis=0,
        )
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1 / n)
        centroids.append(points[rng.choice(n, p=probs)])
    centroids = np.stack(centroids).astype(np.float32)

    for _ in range(n_iters):
        d = ((points[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        labels = d.argmin(axis=1)
        new_cent = np.zeros_like(centroids)
        for j in range(k):
            sel = points[labels == j]
            new_cent[j] = sel.mean(axis=0) if len(sel) else centroids[j]
        if np.allclose(new_cent, centroids, atol=0.5):
            break
        centroids = new_cent
    return labels, centroids


def cluster_to_grid(colors: np.ndarray, n: int, max_seeds: int = 20) -> np.ndarray:
    """K-means 聚类. 多种子尝试: 优先唯一解; 否则任意可解; 都不行用 seed=0 兜底."""
    from cow_puzzle import count_solutions
    flat = colors.reshape(-1, 3)
    best_solvable = None
    for seed in range(max_seeds):
        labels, _ = kmeans(flat, n, seed=seed)
        grid = labels.reshape(n, n)
        c = count_solutions(grid.tolist(), limit=2)
        if c == 1:
            return grid
        if c >= 1 and best_solvable is None:
            best_solvable = grid
    if best_solvable is not None:
        return best_solvable
    labels, _ = kmeans(flat, n, seed=0)
    return labels.reshape(n, n)


# ---------------- 输出 ----------------

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def grid_to_text(grid: np.ndarray) -> str:
    return "\n".join("".join(DIGITS[int(v)] for v in row) for row in grid)


def save_debug(img: np.ndarray, bbox, n, grid, out_path: str) -> None:
    left, top, right, bot = bbox
    cell_w = (right - left + 1) / n
    cell_h = (bot - top + 1) / n
    im = Image.fromarray(img).convert("RGB")
    draw = ImageDraw.Draw(im)
    draw.rectangle([left, top, right, bot], outline="red", width=3)
    for r in range(n):
        for c in range(n):
            cx = int(left + (c + 0.5) * cell_w)
            cy = int(top + (r + 0.5) * cell_h)
            ch = DIGITS[int(grid[r, c])]
            draw.text((cx - 5, cy - 7), ch, fill="black")
    im.save(out_path)


def save_solution_overlay(img: np.ndarray, bbox, n, solution, out_path: str) -> None:
    """在原图上画牛位 (红色圆点)."""
    left, top, right, bot = bbox
    cell_w = (right - left + 1) / n
    cell_h = (bot - top + 1) / n
    im = Image.fromarray(img).convert("RGB")
    draw = ImageDraw.Draw(im)
    radius = int(min(cell_w, cell_h) * 0.28)
    for r, c in solution:
        cx = int(left + (c + 0.5) * cell_w)
        cy = int(top + (r + 0.5) * cell_h)
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=(255, 60, 60), outline=(0, 0, 0), width=5,
        )
    im.save(out_path)


def save_grid_image(grid: np.ndarray, solution, out_path: str,
                    cell_px: int = 80) -> None:
    """纯净格子图: 每格按 cluster 上色, 牛位画黑圈."""
    n = grid.shape[0]
    palette = [
        (235, 175, 188), (252, 188, 152), (255, 220, 130), (177, 222, 175),
        (160, 210, 220), (170, 180, 230), (200, 175, 220), (240, 175, 215),
        (200, 220, 175), (220, 200, 165), (175, 220, 200), (210, 195, 230),
        (130, 170, 200), (200, 130, 160), (165, 180, 130), (135, 200, 175),
    ]
    pad = 2
    W = n * cell_px + (n + 1) * pad
    im = Image.new("RGB", (W, W), (250, 250, 250))
    draw = ImageDraw.Draw(im)
    for r in range(n):
        for c in range(n):
            x0 = pad + c * (cell_px + pad)
            y0 = pad + r * (cell_px + pad)
            color = palette[int(grid[r, c]) % len(palette)]
            draw.rounded_rectangle(
                [x0, y0, x0 + cell_px, y0 + cell_px],
                radius=cell_px // 6, fill=color,
            )
    cows = set(tuple(p) for p in solution) if solution else set()
    for r, c in cows:
        x0 = pad + c * (cell_px + pad)
        y0 = pad + r * (cell_px + pad)
        cx = x0 + cell_px // 2
        cy = y0 + cell_px // 2
        rad = cell_px // 3
        draw.ellipse(
            [cx - rad, cy - rad, cx + rad, cy + rad],
            fill=(50, 50, 50), outline=(255, 255, 255), width=3,
        )
    im.save(out_path)


# ---------------- CLI ----------------

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    path = args[0]
    n_override = None
    out_path = None
    debug_path = None
    solve_overlay = None
    grid_img = None
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--n":
            n_override = int(args[i + 1]); i += 2
        elif a in ("-o", "--out"):
            out_path = args[i + 1]; i += 2
        elif a == "--debug":
            debug_path = args[i + 1]; i += 2
        elif a == "--overlay":
            solve_overlay = args[i + 1]; i += 2
        elif a == "--grid-img":
            grid_img = args[i + 1]; i += 2
        else:
            i += 1

    img = np.array(Image.open(path).convert("RGB"))
    bbox = find_board_bbox(img)
    n = n_override or detect_n(img, bbox)
    print(f"[image_to_grid] bbox={bbox}  N={n}", file=sys.stderr)

    colors = sample_cells(img, bbox, n)
    grid = cluster_to_grid(colors, n)
    text = grid_to_text(grid)

    if out_path:
        Path(out_path).write_text(text + "\n", encoding="utf-8")
        print(f"[image_to_grid] 写入 {out_path}", file=sys.stderr)
    else:
        print(text)
    if debug_path:
        save_debug(img, bbox, n, grid, debug_path)
        print(f"[image_to_grid] 调试图 -> {debug_path}", file=sys.stderr)
    if solve_overlay or grid_img:
        from cow_puzzle import solve
        sol = solve(grid.tolist())
        if sol is None:
            print("[image_to_grid] 无解", file=sys.stderr)
            return
        print(f"[image_to_grid] 解: {sol}", file=sys.stderr)
        if solve_overlay:
            save_solution_overlay(img, bbox, n, sol, solve_overlay)
            print(f"[image_to_grid] 叠加图 -> {solve_overlay}", file=sys.stderr)
        if grid_img:
            save_grid_image(grid, sol, grid_img)
            print(f"[image_to_grid] 格子图 -> {grid_img}", file=sys.stderr)


if __name__ == "__main__":
    main()
