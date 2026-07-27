"""ScreenSpot 零样本评测 — 支持 ShowUI-2B 和 API VLM。

用法:
    # 使用 ShowUI-2B（默认）
    python scripts/run_screenspot_eval.py

    # 使用 ShowUI-2B，只跑 web 子集
    python scripts/run_screenspot_eval.py --quick

    # 使用 API VLM
    python scripts/run_screenspot_eval.py --grounder api

    # 指定每类最多跑 N 条
    python scripts/run_screenspot_eval.py --max-samples 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_annotations(ann_path: str, img_root: Path, max_samples: int | None = None) -> list[dict]:
    """加载 ScreenSpot JSON 标注文件。"""
    with open(ann_path, encoding="utf-8") as f:
        data = json.load(f)

    samples = []
    for item in data[:max_samples]:
        samples.append({
            "image_path": str(img_root / item["img_filename"]),
            "instruction": item["instruction"],
            "bbox": item["bbox"],
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


def get_image_size(image_path: str) -> tuple[int, int]:
    """快速获取图片尺寸。"""
    with Image.open(image_path) as img:
        return img.size


def create_grounder(grounder_type: str):
    """创建定位器实例。"""
    if grounder_type == "showui":
        from gui_agent.grounding.showui_grounder import ShowUIGrounder
        return ShowUIGrounder()
    elif grounder_type == "api":
        from gui_agent.grounding.visual_grounder import VisualGrounder
        from gui_agent.llm.factory import create_default_vlm
        model = create_default_vlm()
        if model is None:
            print("[FAIL] API VLM 未配置。请设置环境变量。")
            sys.exit(1)
        return VisualGrounder(vlm_model=model)
    else:
        raise ValueError(f"未知的 grounder 类型: {grounder_type}")


def evaluate_split(grounder, samples: list[dict], report_interval: int = 50) -> dict:
    """评测一个批次的样本。"""
    stats = {
        "total": 0, "hit": 0, "by_source": {}, "by_type": {},
        "errors": 0, "total_time_s": 0.0,
    }

    for idx, sample in enumerate(samples):
        start = time.perf_counter()
        try:
            result = grounder.predict(
                screenshot_path=sample["image_path"],
                query=sample["instruction"],
            )
        except Exception:
            stats["errors"] += 1
            continue
        elapsed = time.perf_counter() - start
        stats["total_time_s"] += elapsed

        stats["total"] += 1
        img_size = get_image_size(sample["image_path"])
        is_hit = result.point is not None and point_in_bbox(
            result.point, sample["bbox"], img_size
        )
        if is_hit:
            stats["hit"] += 1

        source = sample["data_source"]
        stats["by_source"].setdefault(source, {"total": 0, "hit": 0})
        stats["by_source"][source]["total"] += 1
        if is_hit:
            stats["by_source"][source]["hit"] += 1

        dtype = sample["data_type"]
        stats["by_type"].setdefault(dtype, {"total": 0, "hit": 0})
        stats["by_type"][dtype]["total"] += 1
        if is_hit:
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
    parser = argparse.ArgumentParser(description="ScreenSpot 零样本评测")
    parser.add_argument("--grounder", type=str, default="showui",
                        choices=["showui", "api"], help="定位器类型")
    parser.add_argument("--quick", action="store_true", help="只跑 web 子集")
    parser.add_argument("--max-samples", type=int, default=None, help="每类最多跑 N 条")
    args = parser.parse_args()

    # 创建定位器
    print(f"定位器: {args.grounder}")
    grounder = create_grounder(args.grounder)
    print()

    # 数据目录
    img_root = ROOT / "data" / "ScreenSpot" / "images"

    # 选择评测文件
    if args.quick:
        ann_files = ["screenspot_web.json"]
    else:
        ann_files = ["screenspot_web.json", "screenspot_mobile.json", "screenspot_desktop.json"]

    # 逐批评测
    all_stats = {"total": 0, "hit": 0, "errors": 0, "total_time_s": 0.0}

    for ann_file in ann_files:
        ann_path = ROOT / "data" / "ScreenSpot" / "annotations" / ann_file
        if not ann_path.exists():
            print(f"[SKIP] {ann_file} 不存在，跳过。")
            continue

        samples = load_annotations(str(ann_path), img_root, max_samples=args.max_samples)
        split_name = ann_file.replace("screenspot_", "").replace(".json", "")
        print(f"正在评测: {split_name}（{len(samples)} 样本）")

        stats = evaluate_split(grounder, samples)
        print_results(split_name, stats)

        all_stats["total"] += stats["total"]
        all_stats["hit"] += stats["hit"]
        all_stats["errors"] += stats["errors"]
        all_stats["total_time_s"] += stats["total_time_s"]

    # 汇总
    if all_stats["total"]:
        total_acc = all_stats["hit"] / all_stats["total"] * 100
        avg_time = all_stats["total_time_s"] / all_stats["total"]
        print(f"\n{'='*50}")
        print(f"  最终汇总")
        print(f"{'='*50}")
        print(f"  Grounder:   {args.grounder}")
        print(f"  总样本:     {all_stats['total']}")
        print(f"  总命中:     {all_stats['hit']}")
        print(f"  总错误:     {all_stats['errors']}")
        print(f"  总准确率:   {total_acc:.1f}%")
        print(f"  平均耗时:   {avg_time:.2f}s/样本")
        print(f"{'='*50}")
    else:
        print("\n[WARN] 没有样本被评测，请检查数据路径。")


if __name__ == "__main__":
    main()