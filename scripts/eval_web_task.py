"""真实网页操作评测 — 验证 ShowUI-2B 的视觉理解、定位与动作执行能力。

评测流程：
1. 打开目标网页
2. 拍照 → ShowUI 预测下一步动作 → 执行 → 记录
3. 重复直到任务完成或超步
4. 保存截图、标注、结果和分析报告
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── 配置 ──

TASK_CONFIG = {
    "task": "Search for 'Artificial intelligence' on Wikipedia. "
            "First click the search box, type the query, then click the search button.",
    "start_url": "https://en.wikipedia.org/wiki/Main_Page",
    "success_url_substring": "Artificial_intelligence",
    "max_steps": 6,
    "window_size": (1280, 900),
    "headless": False,  # 设为 True 可无头运行
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / f"web_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# ── 工具函数 ──


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def annotate_screenshot(
    screenshot_path: str,
    output_path: str,
    step_index: int,
    action: dict | None = None,
    predicted_point: tuple[float, float] | None = None,
    window_size: tuple[int, int] = (1280, 900),
) -> None:
    """在截图上标注预测位置和步骤信息。"""
    img = Image.open(screenshot_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = window_size

    # 步骤编号
    draw.text((10, 10), f"Step {step_index}", fill=(255, 0, 0), stroke_width=2)

    # 标注动作
    if action:
        action_text = action.get("action", "?")
        draw.text((10, 30), f"Action: {action_text}", fill=(0, 0, 255))

    # 标注预测点
    if predicted_point:
        px = int(predicted_point[0] * w)
        py = int(predicted_point[1] * h)
        # 绘制十字标记
        r = 8
        draw.ellipse([px - r, py - r, px + r, py + r], outline=(255, 0, 0), width=3)
        draw.line([px - r * 2, py, px + r * 2, py], fill=(255, 0, 0), width=2)
        draw.line([px, py - r * 2, px, py + r * 2], fill=(255, 0, 0), width=2)
        # 坐标标注
        coord_text = f"[{predicted_point[0]:.3f}, {predicted_point[1]:.3f}]"
        draw.text((px + 12, py - 10), coord_text, fill=(255, 0, 0))

    img.save(output_path)


# ── 主评测逻辑 ──


def main() -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    from gui_agent.grounding.showui_grounder import ShowUIGrounder

    # 创建输出目录
    out = ensure_dir(OUTPUT_DIR)
    screenshots_dir = ensure_dir(out / "screenshots")
    annotated_dir = ensure_dir(out / "annotated")

    # 初始化 ShowUI
    print("加载 ShowUI-2B...")
    grounder = ShowUIGrounder(mode="navigation")

    # 打开浏览器
    print(f"打开 {TASK_CONFIG['start_url']}...")
    options = webdriver.ChromeOptions()
    if TASK_CONFIG["headless"]:
        options.add_argument("--headless=new")
    ws = TASK_CONFIG["window_size"]
    options.add_argument(f"--window-size={ws[0]},{ws[1]}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(ws[0], ws[1])
    driver.get(TASK_CONFIG["start_url"])
    time.sleep(2)

    # 评测记录
    history: list[dict] = []
    steps: list[dict] = []
    task_completed = False
    max_steps = TASK_CONFIG["max_steps"]
    success_url = TASK_CONFIG["success_url_substring"]

    print(f"\n{'='*60}")
    print(f"  任务: {TASK_CONFIG['task']}")
    print(f"  最大步数: {max_steps}")
    print(f"{'='*60}\n")

    for step_idx in range(1, max_steps + 1):
        print(f"\n--- Step {step_idx} ---")

        # 1. 截图
        screenshot_path = str(screenshots_dir / f"step_{step_idx}.png")
        driver.save_screenshot(screenshot_path)
        current_url = driver.current_url

        # 2. 检查是否成功
        if success_url and success_url in current_url:
            print(f"  ✅ 任务完成！URL 包含 '{success_url}'")
            task_completed = True
            break

        # 3. ShowUI 预测动作
        try:
            result = grounder.predict_action(
                screenshot_path=screenshot_path,
                task=TASK_CONFIG["task"],
                device_type="web",
                history=history,
            )
        except Exception as e:
            print(f"  ❌ ShowUI 预测失败: {e}")
            steps.append({
                "step": step_idx,
                "action": "ERROR",
                "error": str(e),
                "url": current_url,
            })
            continue

        action_type = result.get("action", "STOP")
        value = result.get("value")
        position = result.get("position")

        print(f"  ShowUI 输出: {result}")
        print(f"  动作: {action_type}")
        if position:
            print(f"  坐标: {position}")
        if value:
            print(f"  值: {value}")

        # 4. 执行动作
        action_success = True
        action_error = None

        try:
            if action_type == "CLICK" and position:
                x = int(position[0] * ws[0])
                y = int(position[1] * ws[1])
                print(f"  执行点击: ({x}, {y})")
                driver.execute_script(
                    "var el = document.elementFromPoint(arguments[0], arguments[1]);"
                    "if (el) { el.focus(); el.click(); }",
                    x, y,
                )
                time.sleep(1.5)

            elif action_type == "INPUT" and position:
                if position:
                    x = int(position[0] * ws[0])
                    y = int(position[1] * ws[1])
                    print(f"  先点击输入框: ({x}, {y})")
                    driver.execute_script(
                        "var el = document.elementFromPoint(arguments[0], arguments[1]);"
                        "if (el) { el.focus(); el.click(); }",
                        x, y,
                    )
                    time.sleep(0.5)
                if value:
                    print(f"  输入: {value}")
                    active = driver.switch_to.active_element
                    if active:
                        active.clear()
                        active.send_keys(value)
                        time.sleep(1)

            elif action_type == "ENTER":
                print("  按 Enter")
                active = driver.switch_to.active_element
                if active:
                    active.send_keys(Keys.ENTER)
                time.sleep(2)

            elif action_type == "SCROLL":
                direction = value or "down"
                scroll_y = 400 if direction == "down" else -400
                driver.execute_script(f"window.scrollBy(0, {scroll_y});")
                time.sleep(1)

            elif action_type == "STOP":
                print("  STOP 动作，结束")
                break

            elif action_type == "ANSWER":
                print(f"  ANSWER: {value}")
                task_completed = True
                break

            else:
                print(f"  未知动作: {action_type}，跳过")

        except Exception as e:
            action_success = False
            action_error = str(e)
            print(f"  ❌ 执行失败: {action_error}")

        # 5. 记录步骤
        step_record = {
            "step": step_idx,
            "action": action_type,
            "value": value,
            "predicted_position": position,
            "action_success": action_success,
            "action_error": action_error,
            "url": driver.current_url,
            "screenshot": f"screenshots/step_{step_idx}.png",
        }
        steps.append(step_record)

        # 更新历史
        history.append({
            "action": action_type,
            "value": value,
            "position": position,
        })

        # 6. 标注截图
        annotated_path = str(annotated_dir / f"step_{step_idx}.png")
        pred_point = (position[0], position[1]) if position and len(position) == 2 else None
        annotate_screenshot(
            screenshot_path, annotated_path, step_idx,
            action=result, predicted_point=pred_point, window_size=ws,
        )

        # 检查是否在最后一步后成功
        if success_url and success_url in driver.current_url:
            print(f"  ✅ 任务完成！URL 包含 '{success_url}'")
            task_completed = True
            break

    # 最终截图
    final_screenshot = str(screenshots_dir / "final.png")
    driver.save_screenshot(final_screenshot)
    if task_completed:
        final_annotated = str(annotated_dir / "final.png")
        Image.open(final_screenshot).convert("RGB").save(final_annotated)

    driver.quit()

    # ── 保存结果 ──

    # task.json
    task_info = {
        "task": TASK_CONFIG["task"],
        "start_url": TASK_CONFIG["start_url"],
        "success_url_substring": success_url,
        "max_steps": max_steps,
        "window_size": ws,
        "timestamp": datetime.now().isoformat(),
    }
    with open(out / "task.json", "w", encoding="utf-8") as f:
        json.dump(task_info, f, indent=2, ensure_ascii=False)

    # result.json
    try:
        final_url = driver.current_url
    except Exception:
        final_url = history[-1].get("url", "") if history else ""
    result = {
        "task": TASK_CONFIG["task"],
        "completed": task_completed,
        "total_steps": len(steps),
        "steps": steps,
        "final_url": final_url,
    }
    with open(out / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # ── 分析报告 ──

    print(f"\n{'='*60}")
    print(f"  评测报告")
    print(f"{'='*60}")
    print(f"  任务: {TASK_CONFIG['task']}")
    print(f"  完成状态: {'✅ 成功' if task_completed else '❌ 失败'}")
    print(f"  总步数: {len(steps)}")
    print(f"  最终 URL: {driver.current_url}")
    print()

    print(f"  步骤分析:")
    for s in steps:
        pos_info = ""
        if s["predicted_position"]:
            pos_info = f" @ [{s['predicted_position'][0]:.3f}, {s['predicted_position'][1]:.3f}]"
        status = "✅" if s["action_success"] else "❌"
        print(f"    Step {s['step']}: {status} {s['action']}{pos_info}")
        if s["value"]:
            print(f"       value: {s['value']}")
        if s["action_error"]:
            print(f"       error: {s['action_error']}")

    print()
    print(f"  输出目录: {out}")
    print(f"  ├── task.json")
    print(f"  ├── result.json")
    print(f"  ├── screenshots/  ({len(steps) + 1} 张)")
    print(f"  └── annotated/    ({len(steps) + (1 if task_completed else 0)} 张)")
    print(f"{'='*60}")

    # 保存分析报告
    report = {
        "task": TASK_CONFIG["task"],
        "completed": task_completed,
        "total_steps": len(steps),
        "successful_actions": sum(1 for s in steps if s["action_success"]),
        "failed_actions": sum(1 for s in steps if not s["action_success"]),
        "step_details": steps,
        "analysis": {
            "visual_understanding": "评估模型能否理解页面布局和元素",
            "target_localization": "评估模型预测坐标与目标元素的匹配度",
            "action_planning": "评估模型能否规划正确的操作序列",
        },
        "final_url": driver.current_url,
    }
    with open(out / "analysis.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n报告已保存到 outputs/ 目录")


if __name__ == "__main__":
    main()