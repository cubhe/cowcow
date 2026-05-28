# 🐮 cowcow — 极限找牛 求解器 + 在线试玩

一个 LinkedIn Queens / Star Battle 类约束求解 puzzle 的 **浏览器试玩** + **截图自动求解管线**。

**🎮 在线玩**: https://cubhe.github.io/cowcow/

[English below](#-cowcow--linkedin-queens-style-puzzle-solver--playground)

---

## 玩法

N×N 网格上放 N 头牛，满足:
- 每**行**、每**列**、每种**颜色区域** 恰好 1 头牛
- 任意两头牛不能 8-邻接 (含对角)

### 操作
- **拖拽鼠标**: 把路过的格子标 ✕
- **双击格子**: 放 / 移除 🐮
- 单击 (不拖): toggle 单格 ✕
- 右键: 清空该格
- 每头放下去的牛右上角有 ✓/✕ 徽章: **绿✓ = 与唯一解吻合**, **红✕ = 错位**

### 关卡
浏览器端实时生成唯一解谜题。刷新页面 = 新题。下拉选 5×5 到 10×10。

---

## 项目结构

```
cowcow/
├── index.html          # 在线试玩 (单文件, GitHub Pages 入口)
├── play.html           # 同 index.html, 本地双击打开用
├── cow_puzzle.py       # Python 求解器 + 出题器
├── image_to_grid.py    # 截图 → 文本盘面 (k-means 聚类 + bbox 检测)
├── solve.py            # 便捷入口: 监听文件夹自动解新图
└── puzzles/            # 真实游戏截图样本 + 解码盘面 + 渲染解图
```

### 浏览器端 (零依赖)
打开 `index.html` 或部署的 [GitHub Pages 链接](https://cubhe.github.io/cowcow/) 就能玩。
- **生成器**: 随机摆牛 + 洪泛染色 + 唯一性校验, N≤8 同步出题, N≥9 异步
- **求解器**: 按颜色稀有度优先回溯 + 位掩码, N=12 < 1 ms

### Python 管线 (截图自动求解)
依赖: `Pillow`, `numpy`

```bash
# 单张截图 → 文本盘面 + 解
py -3 image_to_grid.py screenshot.png -o grid.txt --grid-img solved.png
py -3 cow_puzzle.py --load grid.txt

# 便捷入口: 处理 puzzles/ 下一个 p{N}.jpg
py -3 solve.py path/to/screenshot.png

# 监听模式: 把新截图丢进 puzzles/ 自动出解
py -3 solve.py --watch
```

性能: 从图片到解的全流程 **60-110 ms / 张** (12×12)。

---

## 关键算法

**求解 O(N!) 但实际 < 1 ms**: 把"按行回溯"改成"**按颜色按稀有度回溯**"。单元格颜色被迫立即定位 → 强约束在搜索树顶端就触发 → 剪枝爆炸式提升。N=12 真实谜题从 150-400 ms 降到 <1 ms (**100-9000× 提速**)。

**截图自动解码**:
1. 降采样 (1/4) + 饱和度密度找盘面 bbox
2. 沿 Y 方向求列均值, 自适应阈值数 cell → 自动得 N
3. 每格 4 边缘中点采样 (避开 X 标记和牛 icon) 取中位色
4. K-means 聚 N 类; 多种子兜底 (优先唯一解)

---

## 部署 GitHub Pages

仓库 push 完后:
1. 进 https://github.com/cubhe/cowcow/settings/pages
2. **Source** 选 `Deploy from a branch`
3. **Branch** 选 `main` / 路径 `/ (root)`
4. 保存. 一两分钟后访问 https://cubhe.github.io/cowcow/

---

## 🐮 cowcow — LinkedIn Queens-Style Puzzle Solver + Playground

A constraint puzzle (LinkedIn Queens / Star Battle variant) with a **browser playground** and a **screenshot-to-solution pipeline**.

**🎮 Play online**: https://cubhe.github.io/cowcow/

### Rules

Place N cows on an N×N grid such that:
- Every **row**, **column**, and **color region** has exactly one cow
- No two cows are 8-adjacent (including diagonals)

### Controls

- **Drag mouse**: mark all passed cells as ✕
- **Double-click**: place / remove 🐮
- Single click (no drag): toggle ✕ on one cell
- Right-click: clear cell
- Each placed cow shows a ✓/✕ badge: **green ✓ = matches the unique solution**, **red ✕ = wrong**

Browser-side generator produces a fresh uniquely-solvable puzzle on every refresh, sizes 5×5 to 10×10.

### Project Layout

```
cowcow/
├── index.html          # Web playground (single file, GitHub Pages entry)
├── play.html           # Same as index.html — open locally
├── cow_puzzle.py       # Python solver + generator
├── image_to_grid.py    # Screenshot → text grid (k-means + bbox detection)
├── solve.py            # Convenience entry: watch folder, auto-solve new images
└── puzzles/            # Real game screenshots + decoded grids + rendered solutions
```

### Python Pipeline (Optional)

Requirements: `Pillow`, `numpy`

```bash
# Single screenshot → text grid + rendered solution
py -3 image_to_grid.py screenshot.png -o grid.txt --grid-img solved.png
py -3 cow_puzzle.py --load grid.txt

# Watch mode: drop a screenshot into puzzles/, it gets solved automatically
py -3 solve.py --watch
```

End-to-end (image → solution): **60-110 ms** per 12×12 image.

### Key Algorithm

**Solver, O(N!) but actually < 1 ms**: switch from "row-by-row backtracking" to "**color-by-color backtracking, ordered by region size**". Cells from single-cell color regions get forced immediately, propagating constraints into the search tree at maximum strength. For N=12 real-world puzzles: 150-400 ms → <1 ms (**100-9000× speedup**).

**Screenshot decoder**:
1. Downsample (1/4) + saturation density to locate board bbox
2. Column-mean along Y axis + adaptive threshold to count cells → automatic N
3. Sample 4 cell-edge midpoints (avoiding X marks and cow icons), take median color
4. K-means cluster into N classes; multi-seed fallback (prefers uniquely-solvable)

### Deploy to GitHub Pages

After pushing the repo:
1. Go to https://github.com/cubhe/cowcow/settings/pages
2. **Source** → `Deploy from a branch`
3. **Branch** → `main`, folder `/ (root)`
4. Save. After ~1-2 min, visit https://cubhe.github.io/cowcow/

---

## License

MIT
