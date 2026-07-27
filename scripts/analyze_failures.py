#!/usr/bin/env python3
"""ScreenSpot 失败样本分析工具 — 收集失败案例，分类错误类型，生成分析报告。

用法:
    python scripts/analyze_failures.py [--quick] [--max-samples N]
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

from gui_agent.grounding.showui_grounder import ShowUIGrounder


# ── 错误类型分类 ──

ERROR_TYPES = {
    "EDGE_BIAS": "边缘偏移 — 预测落在元素边缘附近，未完全命中 bbox",
    "NEAR_MISS": "邻近混淆 — 预测落在邻近同类元素上（如相邻按钮/图标）",
    "WRONG_ELEMENT": "元素误判 — 预测完全落在错误元素上（类型不同）",
    "CENTER_BIAS": "中心偏置 — 模型倾向于预测到某个固定区域（如页面中心）",
    "OUT_OF_BOUNDS": "越界 — 预测坐标超出图片范围或远离目标",
    "PARSE_ERROR": "解析失败 — 模型输出无法解析为有效坐标",
    "ICON_CONFUSION": "图标混淆 — 未能区分相似图标",
    "TEXT_ERROR": "文本定位错误 — 对 text 类型元素的定位偏差",
}

# 错误类型简写映射
ERROR_TYPE_SHORT = {
    "EDGE_BIAS": "edge_bias",
    "NEAR_MISS": "near_miss",
    "WRONG_ELEMENT": "wrong_element",
    "CENTER_BIAS": "center_bias",
    "OUT_OF_BOUNDS": "out_of_bounds",
    "PARSE_ERROR": "parse_error",
    "ICON_CONFUSION": "icon_confusion",
    "TEXT_ERROR": "text_error",
}


def point_in_bbox(point_norm, bbox_px, img_size):
    """判断归一化坐标点是否落在像素 bbox [x, y, w, h] 内。"""
    img_w, img_h = img_size
    px = point_norm[0] * img_w
    py = point_norm[1] * img_h
    bx, by, bw, bh = bbox_px
    return bx <= px <= bx + bw and by <= py <= by + bh


def get_image_size(image_path: str) -> tuple[int, int]:
    with Image.open(image_path) as img:
        return img.size


def calc_distance(pred, gt_center, img_size):
    """计算预测点与 bbox 中心的归一化距离。"""
    img_w, img_h = img_size
    px = pred[0] * img_w
    py = pred[1] * img_h
    gx, gy = gt_center
    return math.sqrt((px - gx) ** 2 + (py - gy) ** 2)


def calc_bbox_center(bbox):
    """bbox: [x, y, w, h]"""
    return (bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2)


def classify_error_type(sample, pred_point, img_size, debug=False) -> str:
    """根据预测点和真实标注，分类错误类型。"""
    bbox = sample["bbox"]
    bx, by, bw, bh = bbox
    gt_center = calc_bbox_center(bbox)
    img_w, img_h = img_size

    px = pred_point[0] * img_w
    py = pred_point[1] * img_h

    dist = calc_distance(pred_point, gt_center, img_size)
    data_type = sample.get("data_type", "text")

    # 检查是否靠近 bbox 边缘（在 bbox 外但在附近）
    margin = 20  # 像素
    expanded_bbox = (bx - margin, by - margin, bw + 2 * margin, bh + 2 * margin)
    in_expanded = (expanded_bbox[0] <= px <= expanded_bbox[0] + expanded_bbox[2] and
                   expanded_bbox[1] <= py <= expanded_bbox[1] + expanded_bbox[3])

    if in_expanded:
        return "EDGE_BIAS"

    # 检查是否偏向页面中心
    center_x, center_y = img_w / 2, img_h / 2
    center_dist = math.sqrt((px - center_x) ** 2 + (py - center_y) ** 2)
    page_diag = math.sqrt(img_w ** 2 + img_h ** 2)

    # 如果预测点非常靠近页面中心且远离目标
    if center_dist < page_diag * 0.15 and dist > page_diag * 0.2:
        return "CENTER_BIAS"

    # 如果距离很远，属于越界
    if dist > page_diag * 0.4:
        return "OUT_OF_BOUNDS"

    # 对于 icon 类型，且距离中等
    if data_type == "icon" and dist > 50:
        return "ICON_CONFUSION"

    # 对于 text 类型
    if data_type == "text" and dist > 50:
        return "TEXT_ERROR"

    # 距离较近但未命中
    if dist < 100:
        return "NEAR_MISS"

    # 默认
    return "WRONG_ELEMENT"


def load_annotations(ann_path, img_root, max_samples=None):
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


def main():
    parser = argparse.ArgumentParser(description="ScreenSpot 失败样本分析")
    parser.add_argument("--quick", action="store_true", help="只跑 web 子集")
    parser.add_argument("--max-samples", type=int, default=None, help="每类最多跑 N 条")
    args = parser.parse_args()

    # 加载模型
    print("加载 ShowUI-2B...")
    grounder = ShowUIGrounder()
    print()

    # 数据目录
    img_root = ROOT / "data" / "ScreenSpot" / "images"

    if args.quick:
        ann_files = ["screenspot_web.json"]
    else:
        ann_files = ["screenspot_web.json", "screenspot_mobile.json", "screenspot_desktop.json"]

    # 汇总统计
    all_stats = {
        "total": 0, "hit": 0, "errors": 0, "total_time_s": 0.0,
        "by_source": defaultdict(lambda: {"total": 0, "hit": 0}),
        "by_type": defaultdict(lambda: {"total": 0, "hit": 0}),
        "error_types": defaultdict(int),
        "error_by_source": defaultdict(lambda: defaultdict(int)),
        "error_by_type": defaultdict(lambda: defaultdict(int)),
    }

    # 收集失败样本
    failures = []

    for ann_file in ann_files:
        ann_path = ROOT / "data" / "ScreenSpot" / "annotations" / ann_file
        if not ann_path.exists():
            print(f"[SKIP] {ann_file} 不存在，跳过。")
            continue

        samples = load_annotations(str(ann_path), img_root, max_samples=args.max_samples)
        split_name = ann_file.replace("screenspot_", "").replace(".json", "")
        print(f"正在评测: {split_name}（{len(samples)} 样本）")

        for idx, sample in enumerate(samples):
            start = time.perf_counter()
            try:
                result = grounder.predict(
                    screenshot_path=sample["image_path"],
                    query=sample["instruction"],
                )
            except Exception as e:
                all_stats["errors"] += 1
                failures.append({
                    "image_path": sample["image_path"],
                    "instruction": sample["instruction"],
                    "bbox": sample["bbox"],
                    "data_type": sample["data_type"],
                    "data_source": sample["data_source"],
                    "predicted_point": None,
                    "error_type": "PARSE_ERROR",
                    "error_detail": str(e)[:200],
                    "distance_px": None,
                    "hit": False,
                })
                continue

            elapsed = time.perf_counter() - start
            all_stats["total_time_s"] += elapsed
            all_stats["total"] += 1

            img_size = get_image_size(sample["image_path"])
            is_hit = (result.point is not None and
                      point_in_bbox(result.point, sample["bbox"], img_size))

            if is_hit:
                all_stats["hit"] += 1
            else:
                # 分类错误类型
                error_type = classify_error_type(sample, result.point, img_size) if result.point else "PARSE_ERROR"
                all_stats["error_types"][error_type] += 1
                all_stats["error_by_source"][sample["data_source"]][error_type] += 1
                all_stats["error_by_type"][sample["data_type"]][error_type] += 1

                gt_center = calc_bbox_center(sample["bbox"])
                dist = calc_distance(result.point, gt_center, img_size) if result.point else None

                failure = {
                    "image_path": sample["image_path"],
                    "instruction": sample["instruction"],
                    "bbox": sample["bbox"],
                    "data_type": sample["data_type"],
                    "data_source": sample["data_source"],
                    "predicted_point": result.point,
                    "error_type": error_type,
                    "error_detail": ERROR_TYPES.get(error_type, ""),
                    "distance_px": round(dist, 1) if dist else None,
                    "hit": False,
                    "raw_output": result.metadata.get("raw_output", ""),
                }
                failures.append(failure)

            # 统计按 source
            src = sample["data_source"]
            all_stats["by_source"][src]["total"] += 1
            if is_hit:
                all_stats["by_source"][src]["hit"] += 1

            # 统计按 type
            dt = sample["data_type"]
            all_stats["by_type"][dt]["total"] += 1
            if is_hit:
                all_stats["by_type"][dt]["hit"] += 1

            if (idx + 1) % 50 == 0:
                acc = all_stats["hit"] / all_stats["total"] * 100 if all_stats["total"] else 0
                print(f"  进度: {idx+1}/{len(samples)}, 当前准确率: {acc:.1f}%")

        print(f"  {split_name} 完成")

    # ── 生成分析报告 ──

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "outputs" / f"failure_analysis_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    total = all_stats["total"]
    hits = all_stats["hit"]
    acc = hits / total * 100 if total else 0
    avg_time = all_stats["total_time_s"] / total if total else 0

    report = []
    report.append("=" * 70)
    report.append("  ScreenSpot 失败样本分析报告")
    report.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 70)
    report.append("")
    report.append(f"## 一、总体评测结果")
    report.append("")
    report.append(f"| 指标 | 值 |")
    report.append(f"|:----|:---|")
    report.append(f"| 数据集 | ScreenSpot 全量 |")
    report.append(f"| 总样本数 | {total} |")
    report.append(f"| 命中数 | {hits} |")
    report.append(f"| 准确率 | {acc:.1f}% |")
    report.append(f"| 失败数 | {total - hits} |")
    report.append(f"| 解析错误 | {all_stats['errors']} |")
    report.append(f"| 平均耗时 | {avg_time:.2f}s/样本 |")
    report.append("")

    report.append(f"## 二、按平台分析")
    report.append("")
    report.append(f"| 平台 | 样本数 | 命中 | 准确率 | 失败数 | 失败率 |")
    report.append(f"|:----|:------:|:----:|:------:|:------:|:------:|")
    for src in ["web", "mobile", "desktop"]:
        s = all_stats["by_source"].get(src, {"total": 0, "hit": 0})
        sa = s["hit"] / s["total"] * 100 if s["total"] else 0
        sf = s["total"] - s["hit"]
        sfr = sf / s["total"] * 100 if s["total"] else 0
        report.append(f"| {src:8s} | {s['total']:5d} | {s['hit']:4d} | {sa:5.1f}% | {sf:4d} | {sfr:5.1f}% |")
    report.append("")

    report.append(f"## 三、按元素类型分析")
    report.append("")
    report.append(f"| 类型 | 样本数 | 命中 | 准确率 | 失败数 | 失败率 |")
    report.append(f"|:----|:------:|:----:|:------:|:------:|:------:|")
    for dt in ["text", "icon"]:
        s = all_stats["by_type"].get(dt, {"total": 0, "hit": 0})
        da = s["hit"] / s["total"] * 100 if s["total"] else 0
        df = s["total"] - s["hit"]
        dfr = df / s["total"] * 100 if s["total"] else 0
        report.append(f"| {dt:6s} | {s['total']:5d} | {s['hit']:4d} | {da:5.1f}% | {df:4d} | {dfr:5.1f}% |")
    report.append("")

    # 错误类型分布
    report.append(f"## 四、错误类型分布")
    report.append("")
    report.append(f"| 错误类型 | 数量 | 占比 | 说明 |")
    report.append(f"|:--------|:----:|:----:|:-----|")
    sorted_errors = sorted(all_stats["error_types"].items(), key=lambda x: x[1], reverse=True)
    for err_type, count in sorted_errors:
        pct = count / (total - hits) * 100 if total - hits else 0
        desc = ERROR_TYPES.get(err_type, "")
        report.append(f"| {err_type:15s} | {count:4d} | {pct:5.1f}% | {desc} |")
    report.append("")

    # 按平台的错误类型分布
    report.append(f"## 五、按平台的错误类型分布")
    report.append("")
    for src in ["web", "mobile", "desktop"]:
        errs = all_stats["error_by_source"].get(src, {})
        if not errs:
            continue
        total_errs = sum(errs.values())
        report.append(f"### {src} 平台（共 {total_errs} 个错误）")
        report.append("")
        report.append(f"| 错误类型 | 数量 | 占该平台错误比 |")
        report.append(f"|:--------|:----:|:-------------:|")
        for err_type, count in sorted(errs.items(), key=lambda x: x[1], reverse=True):
            pct = count / total_errs * 100 if total_errs else 0
            report.append(f"| {err_type:15s} | {count:4d} | {pct:5.1f}% |")
        report.append("")

    # 按元素类型的错误类型分布
    report.append(f"## 六、按元素类型的错误类型分布")
    report.append("")
    for dt in ["text", "icon"]:
        errs = all_stats["error_by_type"].get(dt, {})
        if not errs:
            continue
        total_errs = sum(errs.values())
        report.append(f"### {dt} 类型（共 {total_errs} 个错误）")
        report.append("")
        report.append(f"| 错误类型 | 数量 | 占该类型错误比 |")
        report.append(f"|:--------|:----:|:-------------:|")
        for err_type, count in sorted(errs.items(), key=lambda x: x[1], reverse=True):
            pct = count / total_errs * 100 if total_errs else 0
            report.append(f"| {err_type:15s} | {count:4d} | {pct:5.1f}% |")
        report.append("")

    # 距离分布分析
    report.append(f"## 七、误差距离分布")
    report.append("")
    dists = [f["distance_px"] for f in failures if f["distance_px"] is not None]
    if dists:
        dists.sort()
        report.append(f"| 指标 | 值（像素） |")
        report.append(f"|:----|:---------:|")
        report.append(f"| 最小误差 | {dists[0]:.1f} |")
        report.append(f"| 最大误差 | {dists[-1]:.1f} |")
        report.append(f"| 中位数误差 | {dists[len(dists)//2]:.1f} |")
        report.append(f"| 平均误差 | {sum(dists)/len(dists):.1f} |")
        report.append("")
        report.append(f"| 距离范围 | 数量 | 占比 |")
        report.append(f"|:--------|:----:|:----:|")
        ranges = [(0, 20), (20, 50), (50, 100), (100, 200), (200, 500), (500, float("inf"))]
        for lo, hi in ranges:
            cnt = sum(1 for d in dists if lo <= d < hi)
            if cnt:
                label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
                report.append(f"| {label:>8}px | {cnt:4d} | {cnt/len(dists)*100:5.1f}% |")
        report.append("")

    # Top-20 最差失败案例
    report.append(f"## 八、Top-20 最差失败案例（按误差距离排序）")
    report.append("")
    worst_failures = sorted(failures, key=lambda f: f["distance_px"] or 0, reverse=True)[:20]
    report.append(f"| # | 指令 | 类型 | 平台 | 真实 bbox | 预测坐标 | 误差(px) | 错误类型 |")
    report.append(f"|:-|:-----|:----|:----|:---------|:---------|:--------:|:--------|")
    for i, f in enumerate(worst_failures, 1):
        inst = f["instruction"][:30]
        bbox_str = f"[{f['bbox'][0]}, {f['bbox'][1]}, {f['bbox'][2]}, {f['bbox'][3]}]"
        pred_str = f"[{f['predicted_point'][0]:.3f}, {f['predicted_point'][1]:.3f}]" if f["predicted_point"] else "N/A"
        dist_str = f"{f['distance_px']:.0f}" if f["distance_px"] else "N/A"
        report.append(f"| {i:2d} | {inst:30s} | {f['data_type']:4s} | {f['data_source']:8s} | {bbox_str:24s} | {pred_str:18s} | {dist_str:>6s} | {f['error_type']:15s} |")
    report.append("")

    # 按指令模式分析
    report.append(f"## 九、指令模式分析")
    report.append("")
    # 按指令关键词分组
    keyword_patterns = {
        "button": ["button", "btn", "click"],
        "icon": ["icon", "logo", "avatar", "profile"],
        "search": ["search", "find", "lookup"],
        "input": ["input", "type", "enter", "fill"],
        "menu": ["menu", "dropdown", "select"],
        "link": ["link", "goto", "navigate"],
        "close": ["close", "exit", "cancel", "delete", "remove"],
        "scroll": ["scroll", "up", "down"],
    }
    instruction_errors = defaultdict(int)
    instruction_total = defaultdict(int)
    for f in failures:
        inst_lower = f["instruction"].lower()
        for pattern, keywords in keyword_patterns.items():
            if any(k in inst_lower for k in keywords):
                instruction_errors[pattern] += 1
                break
    # 统计总数
    for sample in load_annotations(str(ROOT / "data" / "ScreenSpot" / "annotations" / "screenspot_web.json"), img_root):
        pass  # Just for reference
    # 直接用所有样本统计
    all_instructions = []
    for ann_file in ann_files:
        ann_path = ROOT / "data" / "ScreenSpot" / "annotations" / ann_file
        with open(ann_path) as f:
            all_instructions.extend(json.load(f))

    for item in all_instructions:
        inst_lower = item["instruction"].lower()
        for pattern, keywords in keyword_patterns.items():
            if any(k in inst_lower for k in keywords):
                instruction_total[pattern] += 1
                break

    report.append(f"| 指令模式 | 总样本数 | 错误数 | 错误率 |")
    report.append(f"|:--------|:-------:|:------:|:------:|")
    for pattern in sorted(keyword_patterns.keys()):
        total_cnt = instruction_total.get(pattern, 0)
        err_cnt = instruction_errors.get(pattern, 0)
        if total_cnt > 0:
            err_rate = err_cnt / total_cnt * 100
            report.append(f"| {pattern:10s} | {total_cnt:5d} | {err_cnt:4d} | {err_rate:5.1f}% |")
    report.append("")

    # 优化建议
    report.append(f"## 十、优化建议")
    report.append("")
    report.append("基于以上分析，提出以下优化方向：")
    report.append("")

    # 按错误类型给出建议
    for err_type, count in sorted_errors[:5]:
        pct = count / (total - hits) * 100 if total - hits else 0
        if pct < 5:
            continue
        report.append(f"### {err_type}（占比 {pct:.1f}%）")
        report.append("")
        if err_type == "EDGE_BIAS":
            report.append("**问题描述**：模型预测点落在元素边缘附近，未能完全命中 bbox。")
            report.append("**优化方案**：")
            report.append("1. 在训练数据中引入边缘样本增强，添加随机偏移")
            report.append("2. 后处理时结合 DOM 元素位置做交叉验证")
            report.append("3. 使用高斯模糊热力图替代精确坐标点")
            report.append("")
        elif err_type == "NEAR_MISS":
            report.append("**问题描述**：模型预测到邻近的同类元素上，混淆了相邻的相似元素。")
            report.append("**优化方案**：")
            report.append("1. 增加指令的区分度，在 prompt 中加入更多上下文信息")
            report.append("2. 使用多尺度特征融合，提高细粒度区分能力")
            report.append("3. 结合 DOM 结构信息，排除不在目标区域的元素")
            report.append("")
        elif err_type == "WRONG_ELEMENT":
            report.append("**问题描述**：模型完全定位到了错误的元素上。")
            report.append("**优化方案**：")
            report.append("1. 分析是哪些元素被错误定位，检查是否有系统性偏差")
            report.append("2. 增加负样本训练，减少混淆")
            report.append("3. 引入注意力机制的可视化分析，检查模型关注区域")
            report.append("")
        elif err_type == "CENTER_BIAS":
            report.append("**问题描述**：模型倾向于预测到页面中心位置，形成中心偏置。")
            report.append("**优化方案**：")
            report.append("1. 在训练数据中增加非中心元素的样本比例")
            report.append("2. 使用位置编码增强，提高位置感知能力")
            report.append("3. 添加 bias 矫正层，抵消中心偏置")
            report.append("")
        elif err_type == "ICON_CONFUSION":
            report.append("**问题描述**：模型对图标类元素的定位准确率低，容易混淆不同图标。")
            report.append("**优化方案**：")
            report.append("1. 使用 OCR 辅助文本元素的定位")
            report.append("2. 对图标区域进行局部特征增强")
            report.append("3. 收集更多图标类标注数据进行微调")
            report.append("")
    report.append("")
    report.append("---")
    report.append("")
    report.append("*报告由 analyze_failures.py 自动生成*")

    report_text = "\n".join(report)
    report_path = output_dir / "failure_analysis_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已保存到: {report_path}")

    # 保存详细数据
    data_path = output_dir / "failure_details.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": total,
                "hit": hits,
                "accuracy": round(acc, 1),
                "failures": total - hits,
                "errors": all_stats["errors"],
                "avg_time": round(avg_time, 2),
            },
            "by_source": dict(all_stats["by_source"]),
            "by_type": dict(all_stats["by_type"]),
            "error_types": dict(all_stats["error_types"]),
            "error_by_source": {k: dict(v) for k, v in all_stats["error_by_source"].items()},
            "error_by_type": {k: dict(v) for k, v in all_stats["error_by_type"].items()},
            "failures": failures,
        }, f, indent=2, ensure_ascii=False)
    print(f"详细数据已保存到: {data_path}")

    # 打印摘要
    print(f"\n{'='*50}")
    print(f"  分析摘要")
    print(f"{'='*50}")
    print(f"  总样本:     {total}")
    print(f"  命中:       {hits}")
    print(f"  准确率:     {acc:.1f}%")
    print(f"  失败数:     {total - hits}")
    print(f"  错误:       {all_stats['errors']}")
    print(f"  平均耗时:   {avg_time:.2f}s/样本")
    print()
    print(f"  错误类型分布:")
    for err_type, count in sorted_errors:
        print(f"    {err_type:20s}: {count:4d} ({count/(total-hits)*100:5.1f}%)")
    print()
    print(f"  输出目录: {output_dir}")


if __name__ == "__main__":
    main()