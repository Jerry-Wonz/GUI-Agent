#!/usr/bin/env python3
"""ScreenSpot 消融实验评测 — 对比原始 ShowUI 与增强版 Grounder。

用法:
    # 只跑增强版
    python scripts/run_ablation_eval.py --enhanced

    # 只跑原始版
    python scripts/run_ablation_eval.py --baseline

    # 全部对比（默认）
    python scripts/run_ablation_eval.py

    # 快速模式（只跑 web）
    python scripts/run_ablation_eval.py --quick

    # 指定实验编号
    python scripts/run_ablation_eval.py --experiment E1
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def point_in_bbox(point_norm, bbox_px, img_size):
    img_w, img_h = img_size
    px = point_norm[0] * img_w
    py = point_norm[1] * img_h
    bx, by, bw, bh = bbox_px
    return bx <= px <= bx + bw and by <= py <= by + bh


def get_image_size(image_path):
    with Image.open(image_path) as img:
        return img.size


def calc_distance(pred, bbox):
    """计算预测点与 bbox 中心的像素距离。"""
    bx, by, bw, bh = bbox
    cx, cy = bx + bw / 2, by + bh / 2
    return math.sqrt((pred[0] * img_w - cx) ** 2 + (pred[1] * img_h - cy) ** 2)


def load_annotations(ann_path, img_root, max_samples=None):
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


def create_grounder(grounder_type: str, **kwargs):
    """创建定位器实例。"""
    if grounder_type == "baseline":
        from gui_agent.grounding.showui_grounder import ShowUIGrounder
        return ShowUIGrounder(**kwargs)
    elif grounder_type == "enhanced":
        from gui_agent.grounding.showui_enhanced_grounder import ShowUIEnhancedGrounder
        return ShowUIEnhancedGrounder(**kwargs)
    elif grounder_type == "enhanced_no_multiscale":
        from gui_agent.grounding.showui_enhanced_grounder import ShowUIEnhancedGrounder
        return ShowUIEnhancedGrounder(use_multiscale=False, **kwargs)
    elif grounder_type == "enhanced_no_refine":
        from gui_agent.grounding.showui_enhanced_grounder import ShowUIEnhancedGrounder
        return ShowUIEnhancedGrounder(use_local_refine=False, **kwargs)
    elif grounder_type == "enhanced_no_prompt":
        from gui_agent.grounding.showui_enhanced_grounder import ShowUIEnhancedGrounder
        return ShowUIEnhancedGrounder(use_adaptive_prompt=False, **kwargs)
    elif grounder_type == "enhanced_postproc_only":
        # 仅启用后处理
        from gui_agent.grounding.showui_enhanced_grounder import ShowUIEnhancedGrounder
        return ShowUIEnhancedGrounder(
            use_multiscale=False, use_local_refine=False,
            use_adaptive_prompt=False, **kwargs)
    else:
        raise ValueError(f"未知的 grounder 类型: {grounder_type}")


# 错误类型分类
ERROR_TYPES = {
    "EDGE_BIAS": "边缘偏移",
    "NEAR_MISS": "邻近混淆",
    "WRONG_ELEMENT": "元素误判",
    "CENTER_BIAS": "中心偏置",
    "OUT_OF_BOUNDS": "越界",
    "PARSE_ERROR": "解析失败",
    "ICON_CONFUSION": "图标混淆",
    "TEXT_ERROR": "文本定位错误",
}


def classify_error_type(sample, pred_point, img_size):
    """分类错误类型。"""
    bbox = sample["bbox"]
    bx, by, bw, bh = bbox
    data_type = sample.get("data_type", "text")
    img_w, img_h = img_size

    px = pred_point[0] * img_w
    py = pred_point[1] * img_h
    cx, cy = bx + bw / 2, by + bh / 2
    dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)

    # 检查是否靠近 bbox 边缘
    margin = 20
    expanded = (bx - margin, by - margin, bw + 2 * margin, bh + 2 * margin)
    in_expanded = (expanded[0] <= px <= expanded[0] + expanded[2] and
                   expanded[1] <= py <= expanded[1] + expanded[3])

    if in_expanded:
        return "EDGE_BIAS"

    # 中心偏置检查
    center_x, center_y = img_w / 2, img_h / 2
    center_dist = math.sqrt((px - center_x) ** 2 + (py - center_y) ** 2)
    page_diag = math.sqrt(img_w ** 2 + img_h ** 2)

    if center_dist < page_diag * 0.15 and dist > page_diag * 0.2:
        return "CENTER_BIAS"

    if dist > page_diag * 0.4:
        return "OUT_OF_BOUNDS"

    if data_type == "icon" and dist > 50:
        return "ICON_CONFUSION"

    if data_type == "text" and dist > 50:
        return "TEXT_ERROR"

    if dist < 100:
        return "NEAR_MISS"

    return "WRONG_ELEMENT"


def evaluate(grounder, samples, name=""):
    """评测一批样本，返回详细统计。"""
    stats = {
        "total": 0, "hit": 0, "errors": 0, "total_time_s": 0.0,
        "by_source": defaultdict(lambda: {"total": 0, "hit": 0}),
        "by_type": defaultdict(lambda: {"total": 0, "hit": 0}),
        "error_types": defaultdict(int),
        "error_by_source": defaultdict(lambda: defaultdict(int)),
        "error_by_type": defaultdict(lambda: defaultdict(int)),
        "failures": [],
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
        is_hit = (result.point is not None and
                  point_in_bbox(result.point, sample["bbox"], img_size))

        if is_hit:
            stats["hit"] += 1
        else:
            error_type = classify_error_type(sample, result.point, img_size) if result.point else "PARSE_ERROR"
            stats["error_types"][error_type] += 1
            stats["error_by_source"][sample["data_source"]][error_type] += 1
            stats["error_by_type"][sample["data_type"]][error_type] += 1

            bx, by, bw, bh = sample["bbox"]
            cx, cy = bx + bw / 2, by + bh / 2
            img_w, img_h = img_size
            dist = (math.sqrt((result.point[0] * img_w - cx) ** 2 +
                              (result.point[1] * img_h - cy) ** 2)
                    if result.point else None)

            stats["failures"].append({
                "instruction": sample["instruction"],
                "bbox": sample["bbox"],
                "data_type": sample["data_type"],
                "data_source": sample["data_source"],
                "predicted_point": result.point,
                "error_type": error_type,
                "distance_px": round(dist, 1) if dist else None,
            })

        src = sample["data_source"]
        stats["by_source"][src]["total"] += 1
        if is_hit:
            stats["by_source"][src]["hit"] += 1

        dt = sample["data_type"]
        stats["by_type"][dt]["total"] += 1
        if is_hit:
            stats["by_type"][dt]["hit"] += 1

        if (idx + 1) % 50 == 0:
            acc = stats["hit"] / stats["total"] * 100 if stats["total"] else 0
            print(f"  {name}进度: {idx+1}/{len(samples)}, 准确率: {acc:.1f}%")

    return stats


def print_results(name, stats):
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

    if stats["by_source"]:
        print(f"\n  按平台:")
        for src, s in sorted(stats["by_source"].items()):
            sa = s["hit"] / s["total"] * 100 if s["total"] else 0
            print(f"    {src:12s}: {s['hit']:3d}/{s['total']:3d} = {sa:5.1f}%")

    if stats["by_type"]:
        print(f"\n  按类型:")
        for dt, s in sorted(stats["by_type"].items()):
            da = s["hit"] / s["total"] * 100 if s["total"] else 0
            print(f"    {dt:6s}: {s['hit']:3d}/{s['total']:3d} = {da:5.1f}%")

    if stats["error_types"]:
        print(f"\n  错误类型:")
        total_errs = sum(stats["error_types"].values())
        for etype, count in sorted(stats["error_types"].items(), key=lambda x: x[1], reverse=True):
            pct = count / total_errs * 100 if total_errs else 0
            print(f"    {etype:20s}: {count:4d} ({pct:5.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="ScreenSpot 消融实验评测")
    parser.add_argument("--baseline", action="store_true", help="只跑原始版")
    parser.add_argument("--enhanced", action="store_true", help="只跑增强版")
    parser.add_argument("--quick", action="store_true", help="只跑 web 子集")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--experiment", type=str, default=None,
                        choices=["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"])
    args = parser.parse_args()

    run_baseline = args.baseline or (not args.enhanced and not args.experiment)
    run_enhanced = args.enhanced or (not args.baseline and not args.experiment)

    # 实验配置
    experiment_configs = {
        "E1": {"name": "E1-坐标后处理", "grounder": "enhanced_postproc_only"},
        "E2": {"name": "E2-自适应Prompt", "grounder": "enhanced_no_multiscale",
               "kwargs": {"use_adaptive_prompt": True, "use_local_refine": False}},
        "E3": {"name": "E3-多尺度滑动窗口", "grounder": "enhanced_no_refine",
               "kwargs": {"use_multiscale": True, "use_adaptive_prompt": False}},
        "E4": {"name": "E4-局部特征增强", "grounder": "enhanced_no_multiscale",
               "kwargs": {"use_local_refine": True, "use_adaptive_prompt": False}},
        "E5": {"name": "E5-自适应Prompt+后处理", "grounder": "enhanced_no_multiscale",
               "kwargs": {"use_adaptive_prompt": True, "use_local_refine": False}},
        "E6": {"name": "E6-多尺度+局部增强", "grounder": "enhanced",
               "kwargs": {"use_multiscale": True, "use_local_refine": True, "use_adaptive_prompt": False}},
        "E7": {"name": "E7-全方案组合", "grounder": "enhanced"},
        "E8": {"name": "E8-全方案+严格边缘", "grounder": "enhanced",
               "kwargs": {"edge_buffer": 0.03}},
    }

    # 数据目录
    img_root = ROOT / "data" / "ScreenSpot" / "images"

    if args.quick:
        ann_files = ["screenspot_web.json"]
    else:
        ann_files = ["screenspot_web.json", "screenspot_mobile.json", "screenspot_desktop.json"]

    # 加载所有样本
    all_samples = []
    for ann_file in ann_files:
        ann_path = ROOT / "data" / "ScreenSpot" / "annotations" / ann_file
        if not ann_path.exists():
            continue
        samples = load_annotations(str(ann_path), img_root, max_samples=args.max_samples)
        all_samples.extend(samples)

    print(f"总样本数: {len(all_samples)}")
    print()

    if args.experiment:
        # 单实验模式
        cfg = experiment_configs[args.experiment]
        kwargs = cfg.get("kwargs", {})
        print(f"运行实验: {cfg['name']}")
        grounder = create_grounder(cfg["grounder"], **kwargs)
        print(f"  Grounder: {grounder}")
        stats = evaluate(grounder, all_samples, name=cfg["name"])
        print_results(cfg["name"], stats)
    else:
        # 对比模式
        all_results = {}

        if run_baseline:
            print("加载原始 ShowUI...")
            grounder_baseline = create_grounder("baseline")
            stats_baseline = evaluate(grounder_baseline, all_samples, name="基线")
            all_results["baseline"] = stats_baseline
            print_results("原始 ShowUI (基线)", stats_baseline)
            del grounder_baseline
            import torch
            torch.cuda.empty_cache()

        if run_enhanced:
            print("\n加载增强版 ShowUI...")
            grounder_enhanced = create_grounder("enhanced")
            stats_enhanced = evaluate(grounder_enhanced, all_samples, name="增强版")
            all_results["enhanced"] = stats_enhanced
            print_results("增强版 ShowUI", stats_enhanced)
            del grounder_enhanced

        # 对比报告
        if "baseline" in all_results and "enhanced" in all_results:
            b = all_results["baseline"]
            e = all_results["enhanced"]
            b_acc = b["hit"] / b["total"] * 100 if b["total"] else 0
            e_acc = e["hit"] / e["total"] * 100 if e["total"] else 0

            print(f"\n{'='*60}")
            print(f"  优化前后对比")
            print(f"{'='*60}")
            print(f"  {'指标':20s} {'优化前':>8s} {'优化后':>8s} {'提升':>8s}")
            print(f"  {'-'*48}")
            print(f"  {'总体准确率':20s} {b_acc:>7.1f}% {e_acc:>7.1f}% {e_acc-b_acc:>+7.1f}%")
            print(f"  {'总失败数':20s} {b['total']-b['hit']:>8d} {e['total']-e['hit']:>8d} {(b['total']-b['hit'])-(e['total']-e['hit']):>+8d}")

            # 按类型
            for dt in ["text", "icon"]:
                bs = b["by_type"].get(dt, {"total": 0, "hit": 0})
                es = e["by_type"].get(dt, {"total": 0, "hit": 0})
                ba = bs["hit"] / bs["total"] * 100 if bs["total"] else 0
                ea = es["hit"] / es["total"] * 100 if es["total"] else 0
                print(f"  {dt+'准确率':20s} {ba:>7.1f}% {ea:>7.1f}% {ea-ba:>+7.1f}%")

            # 错误类型变化
            print(f"\n  错误类型变化:")
            all_error_types = set(b["error_types"].keys()) | set(e["error_types"].keys())
            for et in sorted(all_error_types):
                bc = b["error_types"].get(et, 0)
                ec = e["error_types"].get(et, 0)
                print(f"    {et:20s}: {bc:4d} → {ec:4d} ({ec-bc:+d})")

            # 按平台
            print(f"\n  按平台:")
            for src in ["web", "mobile", "desktop"]:
                bs = b["by_source"].get(src, {"total": 0, "hit": 0})
                es = e["by_source"].get(src, {"total": 0, "hit": 0})
                ba = bs["hit"] / bs["total"] * 100 if bs["total"] else 0
                ea = es["hit"] / es["total"] * 100 if es["total"] else 0
                print(f"    {src:10s}: {ba:5.1f}% → {ea:5.1f}% ({ea-ba:+5.1f}%)")

            # 推理速度
            b_speed = b["total_time_s"] / b["total"] if b["total"] else 0
            e_speed = e["total_time_s"] / e["total"] if e["total"] else 0
            print(f"\n  {'推理速度':20s} {b_speed:>7.2f}s {e_speed:>7.2f}s {e_speed-b_speed:>+7.2f}s")

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "outputs" / f"ablation_eval_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存可序列化的结果
    serializable = {}
    for name, stats in all_results.items():
        serializable[name] = {
            "total": stats["total"],
            "hit": stats["hit"],
            "accuracy": round(stats["hit"] / stats["total"] * 100, 1) if stats["total"] else 0,
            "errors": stats["errors"],
            "avg_time": round(stats["total_time_s"] / stats["total"], 3) if stats["total"] else 0,
            "by_source": dict(stats["by_source"]),
            "by_type": dict(stats["by_type"]),
            "error_types": dict(stats["error_types"]),
            "error_by_source": {k: dict(v) for k, v in stats["error_by_source"].items()},
            "error_by_type": {k: dict(v) for k, v in stats["error_by_type"].items()},
            "failures": stats["failures"],
        }

    with open(output_dir / "ablation_results.json", "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存到: {output_dir / 'ablation_results.json'}")


if __name__ == "__main__":
    main()