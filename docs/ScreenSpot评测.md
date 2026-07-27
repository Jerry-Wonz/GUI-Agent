# ScreenSpot 零样本评测指南

> 本文档说明如何使用本项目的 `VisualGrounder` 在 ScreenSpot 数据集上运行零样本 grounding 评测，以量化对标 ShowUI、SeeClick 等模型的定位精度。

---

## 1. 背景

### 1.1 ScreenSpot 是什么

ScreenSpot 是一个 GUI Grounding 评测数据集，包含约 **1200+ 条标注样本**，覆盖 Web、Mobile、Desktop 三个平台。每个样本包含：

- 一张截图（PNG）
- 一句文本指令（如 "search button"、"profile icon"）
- 一个标注框（bbox），标明目标元素在截图中的像素位置

### 1.2 评测任务

**Point Accuracy**（点击点准确率）：给定截图 + 指令，模型预测一个归一化坐标点 `[x, y]`（0-1 范围）。若该点落在标注框内，则算命中。最终按平台和元素类型分组报告准确率。

### 1.3 现有 Model Baseline

| 模型             |    参数量    |    平均精度    |
| :--------------- | :----------: | :-------------: |
| MiniGPT-v2       |      7B      |      5.7%      |
| Qwen-VL          |     9.6B     |      5.2%      |
| GPT-4V           |      —      |      16.2%      |
| Fuyu             |      8B      |      19.5%      |
| CogAgent         |     18B     |      47.4%      |
| SeeClick         |     9.6B     |      53.4%      |
| **ShowUI** | **2B** | **75.1%** |

---

## 2. 准备工作

### 2.1 下载 ScreenSpot 数据集

```bash
# 安装 huggingface-cli（如未安装）
pip install huggingface-hub

# 下载数据集到 data/ScreenSpot（~200MB）
huggingface-cli download benwiesel/ScreenSpot --local-dir data/ScreenSpot
```

或从 SeeClick 官方 GitHub 下载：

```bash
# https://github.com/njucckevin/SeeClick
# 下载后解压至 data/ScreenSpot
```

### 2.2 数据目录结构

```
data/ScreenSpot/
├── images/                     # 截图文件
│   ├── web/                    # 网页截图
│   ├── mobile/                 # 移动端截图
│   └── desktop/                # 桌面端截图
└── annotations/                # JSON 标注文件
    ├── screenspot_web.json
    ├── screenspot_mobile.json
    └── screenspot_desktop.json
```

### 2.3 标注格式

```json
// screenspot_web.json 中的一条样本
{
  "img_filename": "web/xxx.png",
  "instruction": "search button",
  "bbox": [120, 45, 80, 32],       // [x, y, width, height] 像素绝对值
  "data_type": "icon",              // "text" 或 "icon"
  "data_source": "web"              // "web" / "mobile" / "desktop"
}
```

---

## 3. 评测脚本

新建 `scripts/run_screenspot_eval.py`：

```python
"""ScreenSpot 零样本评测 — 使用 VisualGrounder 跑 Point Accuracy。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.grounding.visual_grounder import VisualGrounder
from gui_agent.llm.factory import create_default_vlm


def load_annotations(ann_path: str, img_root: Path) -> list[dict]:
    """加载 ScreenSpot JSON 标注文件。"""
    with open(ann_path, encoding="utf-8") as f:
        data = json.load(f)

    samples = []
    for item in data:
        samples.append({
            "image_path": str(img_root / item["img_filename"]),
            "instruction": item["instruction"],
            "bbox": item["bbox"],  # [x, y, width, height] 像素绝对值
            "data_type": item.get("data_type", "text"),
            "data_source": item.get("data_source", "web"),
        })
    return samples


def point_in_bbox(
    point_norm: list[float],
    bbox_px: list[float],
    img_size: tuple[int, int],
) -> bool:
    """判断归一化坐标点 [0-1, 0-1] 是否落在像素 bbox [x, y, w, h] 内。"""
    img_w, img_h = img_size
    px = point_norm[0] * img_w
    py = point_norm[1] * img_h
    bx, by, bw, bh = bbox_px
    return bx <= px <= bx + bw and by <= py <= by + bh


def evaluate_split(
    grounder: VisualGrounder,
    samples: list[dict],
    default_img_size: tuple[int, int] = (1280, 720),
    report_interval: int = 50,
) -> dict:
    """评测一个批次的样本（如 web/mobile/desktop）。"""
    stats = {
        "total": 0,
        "hit": 0,
        "by_source": {},
        "by_type": {},
        "errors": 0,
        "total_time_s": 0.0,
    }

    for idx, sample in enumerate(samples):
        start = time.perf_counter()
        try:
            result = grounder.predict(
                screenshot_path=sample["image_path"],
                query=sample["instruction"],
            )
        except Exception as exc:
            stats["errors"] += 1
            continue
        elapsed = time.perf_counter() - start
        stats["total_time_s"] += elapsed

        stats["total"] += 1
        if result.point is not None and point_in_bbox(
            result.point, sample["bbox"], default_img_size
        ):
            stats["hit"] += 1

        # 按平台来源统计
        source = sample["data_source"]
        stats["by_source"].setdefault(source, {"total": 0, "hit": 0})
        stats["by_source"][source]["total"] += 1
        if result.point is not None and point_in_bbox(
            result.point, sample["bbox"], default_img_size
        ):
            stats["by_source"][source]["hit"] += 1

        # 按元素类型统计（text / icon）
        dtype = sample["data_type"]
        stats["by_type"].setdefault(dtype, {"total": 0, "hit": 0})
        stats["by_type"][dtype]["total"] += 1
        if result.point is not None and point_in_bbox(
            result.point, sample["bbox"], default_img_size
        ):
            stats["by_type"][dtype]["hit"] += 1

        if (idx + 1) % report_interval == 0:
            acc = stats["hit"] / stats["total"] * 100 if stats["total"] else 0
            print(f"  进度: {idx+1}/{len(samples)}, 当前准确率: {acc:.1f}%")

    return stats


def print_results(name: str, stats: dict) -> None:
    """格式化输出评测结果。"""
    total = stats["total"]
    hits = stats["hit"]
    acc = hits / total * 100 if total else 0
    avg_time = stats["total_time_s"] / total if total else 0

    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    print(f"  总样本:     {total}")
    print(f"  命中:       {hits}")
    print(f"  准确率:     {acc:.1f}%")
    print(f"  错误:       {stats['errors']}")
    print(f"  平均耗时:   {avg_time:.2f}s/样本")
    print()

    if stats["by_source"]:
        print("  按平台来源:")
        for source, s in sorted(stats["by_source"].items()):
            sa = s["hit"] / s["total"] * 100 if s["total"] else 0
            print(f"    {source:12s}: {s['hit']:3d}/{s['total']:3d} = {sa:5.1f}%")

    if stats["by_type"]:
        print("  按元素类型:")
        for dtype, s in sorted(stats["by_type"].items()):
            da = s["hit"] / s["total"] * 100 if s["total"] else 0
            print(f"    {dtype:6s}: {s['hit']:3d}/{s['total']:3d} = {da:5.1f}%")


def main() -> None:
    # 1. 加载 VLM 模型
    model = create_default_vlm()
    if model is None:
        print("[FAIL] 未检测到 LLM/VLM 配置。请设置 GUIAGENT_LLM_BASE_URL / API_KEY / MODEL。")
        sys.exit(1)

    # 2. 创建 VisualGrounder
    grounder = VisualGrounder(vlm_model=model)
    print(f"[OK] VisualGrounder 已加载（模型: {model.__class__.__name__}）\n")

    # 3. 数据目录
    img_root = ROOT / "data" / "ScreenSpot" / "images"

    # 4. 逐批评测
    all_stats = {"total": 0, "hit": 0, "errors": 0}

    for ann_file in ["screenspot_web.json", "screenspot_mobile.json", "screenspot_desktop.json"]:
        ann_path = ROOT / "data" / "ScreenSpot" / "annotations" / ann_file
        if not ann_path.exists():
            print(f"[SKIP] {ann_file} 不存在，跳过。")
            continue

        samples = load_annotations(str(ann_path), img_root)
        split_name = ann_file.replace("screenspot_", "").replace(".json", "")
        print(f"\n正在评测: {split_name}（{len(samples)} 样本）")

        stats = evaluate_split(grounder, samples)
        print_results(split_name, stats)

        all_stats["total"] += stats["total"]
        all_stats["hit"] += stats["hit"]
        all_stats["errors"] += stats["errors"]

    # 5. 汇总
    total_acc = all_stats["hit"] / all_stats["total"] * 100 if all_stats["total"] else 0
    print(f"\n{'='*50}")
    print(f"  最终汇总")
    print(f"{'='*50}")
    print(f"  总样本:     {all_stats['total']}")
    print(f"  总命中:     {all_stats['hit']}")
    print(f"  总错误:     {all_stats['errors']}")
    print(f"  总准确率:   {total_acc:.1f}%")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
```

---

## 4. 运行

```bash
python scripts/run_screenspot_eval.py
```

### 输出示例

```
[OK] VisualGrounder 已加载（模型: OpenAICompatibleVisionModel）

正在评测: web（436 样本）
  进度: 50/436, 当前准确率: 82.0%
  进度: 100/436, 当前准确率: 82.0%
  进度: 150/436, 当前准确率: 82.7%
  进度: 200/436, 当前准确率: 84.5%
  进度: 250/436, 当前准确率: 84.8%
  进度: 300/436, 当前准确率: 79.0%
  进度: 350/436, 当前准确率: 67.7%
  进度: 400/436, 当前准确率: 59.2%

==================================================
  web
==================================================
  总样本:     436
  命中:       237
  准确率:     54.4%
  错误:       0
  平均耗时:   12.33s/样本

  按平台来源:
    forum       :  77/ 89 =  86.5%
    gitlab      :  73/ 89 =  82.0%
    shop        :  61/119 =  51.3%
    tool        :  26/139 =  18.7%
  按元素类型:
    icon  :  97/206 =  47.1%
    text  : 140/230 =  60.9%

==================================================
  最终汇总
==================================================
  总样本:     436
  总命中:     237
  总错误:     0
  总准确率:   54.4%
==================================================
```

---

## 5. 结果解读

### 5.1 与 ShowUI 对标

| 你的成绩          | 对标位置                                    |
| :---------------- | :------------------------------------------ |
| **< 20%**   | 低于 GPT-4V，VisualGrounder 或 VLM 效果不佳 |
| **20-40%**  | 与 GPT-4V / CogAgent 相当，基础可用         |
| **40-55%**  | 达到 SeeClick 水平，强 baseline             |
| **55-75%**  | 接近 ShowUI，有竞争力的 grounding 精度      |
| **> 75%**   | 超过 ShowUI 2B                              |
| **接近 0%** | 检查 VLM 是否输出了正确的 JSON 格式坐标     |

### 5.2 错误分析方向

结果出来后可以进一步分析：

1. **哪些平台的准确率最低？** → Mobile 通常比 Web 难，因为元素更小
2. **Text vs Icon 哪个差？** → Icon 定位更依赖视觉特征，Text 可以靠 OCR
3. **哪些指令的坐标偏差最大？** → 统计平均偏移距离（像素级别）
4. **是否有系统性的坐标偏移？** → 检查预测点是否总是偏向某个方向

### 5.3 常见问题排查

| 现象       | 可能原因                         | 解决方案                                                 |
| :--------- | :------------------------------- | :------------------------------------------------------- |
| 全部未命中 | VLM 输出了像素坐标而非归一化坐标 | 检查`visual_grounder.py` 的 `_validate_point()` 日志 |
| 准确率很低 | VLM 不支持细粒度 GUI 定位        | 尝试更强或专为 GUI 优化的 VLM                            |
| 运行时错误 | 图片路径或编码问题               | 确保路径无中文，图片可正常打开                           |
| 速度太慢   | 1200 次 VLM 调用                 | 先只跑`screenspot_web.json`（436 样本）作为快速评估    |

---

## 6. 进阶：将结果写入报告

评测完成后，可以将结果更新到 `docs/project_report.md` 的实验章节，格式参考：

```markdown
### 4.3 ScreenSpot 零样本评测

| 平台 | 样本数 | 命中 | 准确率 |
|:-----|:------:|:----:|:------:|
| Web | 436 | 237 | 54.4% |
| Mobile | — | — | 待评测 |
| Desktop | — | — | 待评测 |
| **合计** | **436** | **237** | **54.4%** |
```

---

## 参考来源

- ScreenSpot 数据集: https://huggingface.co/datasets/benwiesel/ScreenSpot
- SeeClick 论文: https://arxiv.org/abs/2401.10935
- ShowUI 论文: https://arxiv.org/abs/2411.17465
- 项目 VisualGrounder 实现: `src/gui_agent/grounding/visual_grounder.py`

---

## 7. 实测结果

### 7.1 全量评测结果

> 使用 **ShowUI-2B**（`showlab/ShowUI-2B`）对 ScreenSpot 全量数据集的评测结果。

| 平台 | 样本数 | 命中 | 准确率 | 平均耗时 |
|:----|:------:|:----:|:------:|:--------:|
| Web | 436 | 316 | 72.5% | 0.74s |
| Mobile | 502 | 423 | **84.3%** | 0.70s |
| Desktop | 334 | 237 | 71.0% | 0.61s |
| **合计** | **1272** | **976** | **76.7%** | **0.69s** |

### 7.2 按元素类型

| 类型 | 样本数 | 命中 | 准确率 |
|:----|:------:|:----:|:------:|
| Text | 697 | 596 | **85.5%** |
| Icon | 575 | 380 | 66.1% |

### 7.3 对标分析

| 模型 | 参数量 | 准确率 | 对比 |
|:----|:------:|:------:|:----|
| MiniGPT-v2 | 7B | 5.7% | — |
| Qwen-VL | 9.6B | 5.2% | — |
| GPT-4V | — | 16.2% | — |
| Fuyu | 8B | 19.5% | — |
| CogAgent | 18B | 47.4% | — |
| SeeClick | 9.6B | 53.4% | — |
| 通用 API VLM | — | 54.4% | — |
| **ShowUI-2B（本项目）** | **2B** | **76.7%** | **✅ 超越论文** |
| ShowUI-2B（论文） | 2B | 75.1% | 参考基线 |

### 7.4 结论

1. **准确率 76.7%**，超越论文报告的 75.1%，验证了模型权重和评测流程的正确性
2. Mobile 平台表现最佳（84.3%），Desktop 最低（71.0%）
3. Text 元素（85.5%）显著优于 Icon（66.1%），纯文本定位更可靠
4. 推理速度 0.69s/样本，比通用 API VLM 快 16 倍
5. 无需训练，即插即用

### 7.5 优化方向

| 方向 | 措施 | 状态 | 预期收益 |
|:----|:-----|:----|:--------:|
| DOM 融合 | ShowUI 坐标与 DOM 元素位置交叉验证 | ✅ 已实现 | +3-5% |
| OCR 辅助 | 对 text 元素用 OCR 做文本确认 | ✅ 已实现（默认关闭） | 验证辅助 |
| Navigation 模式 | 端到端动作预测，无需外部 VLM | ✅ 已实现 | 架构简化 |
| 推理加速 | KV cache 复用 + torch.compile | 待实施 | 2x 加速 |
