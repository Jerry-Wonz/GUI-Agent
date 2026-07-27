"""Desktop 风格网页操作评测 — 复杂多步骤导航任务。

任务：打开 Wikipedia 的 "Artificial intelligence" 页面，通过目录导航到 "History" 小节，
然后点击其中的 "The Turing Test" 链接，最后验证页面跳转。

这模拟了 Desktop 场景中常见的"在文档中导航 → 点击内部链接 → 跳转新页面"的流程。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw


TASK_CONFIG = {
    "task": (
        "Go to the Wikipedia page for 'Artificial intelligence'. "
        "Scroll down to find the 'History' section in the table of contents, "
        "click on the 'History' link. "
        "Then in the History section, find and click on the link to 'The Turing Test'."
    ),
    "start_url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
    "success_url_substring": "Turing_test",
    "max_steps": 10,
    "window_size": (1280, 900),
    "headless": False,
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / f"desktop_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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

    draw.text((10, 10), f"Step {step_index}", fill=(255, 0, 0))
    if action:
        action_text = action.get("action", "?")
        draw.text((10, 30), f"Action: {action_text}", fill=(0, 0, 255))
    if predicted_point:
        px = int(predicted_point[0] * w)
        py = int(predicted_point[1] * h)
        r = 8
        draw.ellipse([px - r, py - r, px + r, py + r], outline=(255, 0, 0), width=3)
        draw.line([px - r * 2, py, px + r * 2, py], fill=(255, 0, 0), width=2)
        draw.line([px, py - r * 2, px, py + r * 2], fill=(255, 0, 0), width=2)
        coord_text = f"[{predicted_point[0]:.3f}, {predicted_point[1]:.3f}]"
        draw.text((px + 12, py - 10), coord_text, fill=(255, 0, 0))
    img.save(output_path)


def main() -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from gui_agent.grounding.showui_grounder import ShowUIGrounder

    out = ensure_dir(OUTPUT_DIR)
    screenshots_dir = ensure_dir(out / "screenshots")
    annotated_dir = ensure_dir(out / "annotated")

    print("加载 ShowUI-2B...")
    grounder = ShowUIGrounder(mode="navigation")

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
    time.sleep(3)

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

        screenshot_path = str(screenshots_dir / f"step_{step_idx}.png")
        driver.save_screenshot(screenshot_path)
        current_url = driver.current_url

        if success_url and success_url in current_url:
            print(f"  ✅ 任务完成！URL 包含 '{success_url}'")
            task_completed = True
            break

        try:
            body_text = driver.find_element("tag name", "body").text.lower()
            if "captcha" in body_text or "验证码" in body_text:
                print("  ⚠️ 检测到验证码页面，等待人工验证...")
                input("  请在浏览器中完成验证后按 Enter 继续...")
                continue
        except Exception:
            pass

        try:
            result = grounder.predict_action(
                screenshot_path=screenshot_path,
                task=TASK_CONFIG["task"],
                device_type="web",
                history=history,
            )
        except Exception as e:
            print(f"  ❌ ShowUI 预测失败: {e}")
            steps.append({"step": step_idx, "action": "ERROR", "error": str(e), "url": current_url})
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
                time.sleep(2.5)

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
                        time.sleep(1.5)

            elif action_type == "ENTER":
                print("  按 Enter")
                active = driver.switch_to.active_element
                if active:
                    active.send_keys(Keys.ENTER)
                time.sleep(2.5)

            elif action_type == "SCROLL":
                direction = value or "down"
                scroll_y = 500 if direction == "down" else -500
                driver.execute_script(f"window.scrollBy(0, {scroll_y});")
                time.sleep(1.5)

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

        step_record = {
            "step": step_idx,
            "action": action_type,
            "value": value,
            "predicted_position": position,
            "action_success": action_success,
            "action_error": action_error,
            "url": driver.current_url,
        }
        steps.append(step_record)

        history.append({
            "action": action_type,
            "value": value,
            "position": position,
        })

        annotated_path = str(annotated_dir / f"step_{step_idx}.png")
        pred_point = (position[0], position[1]) if position and len(position) == 2 else None
        annotate_screenshot(
            screenshot_path, annotated_path, step_idx,
            action=result, predicted_point=pred_point, window_size=ws,
        )

        if success_url and success_url in driver.current_url:
            print(f"  ✅ 任务完成！URL 包含 '{success_url}'")
            task_completed = True
            break

    final_screenshot = str(screenshots_dir / "final.png")
    driver.save_screenshot(final_screenshot)
    if task_completed:
        Image.open(final_screenshot).convert("RGB").save(str(annotated_dir / "final.png"))

    try:
        final_url = driver.current_url
    except Exception:
        final_url = history[-1].get("url", "") if history else ""
    driver.quit()

    # 保存结果
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

    result = {
        "task": TASK_CONFIG["task"],
        "completed": task_completed,
        "total_steps": len(steps),
        "steps": steps,
        "final_url": final_url,
    }
    with open(out / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    analysis = {
        "task": TASK_CONFIG["task"],
        "completed": task_completed,
        "total_steps": len(steps),
        "successful_actions": sum(1 for s in steps if s["action_success"]),
        "failed_actions": sum(1 for s in steps if not s["action_success"]),
        "final_url": final_url,
    }
    with open(out / "analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    # 输出报告
    print(f"\n{'='*60}")
    print(f"  Desktop 评测报告")
    print(f"{'='*60}")
    print(f"  任务: {TASK_CONFIG['task']}")
    print(f"  完成状态: {'✅ 成功' if task_completed else '❌ 失败'}")
    print(f"  总步数: {len(steps)}")
    print(f"  最终 URL: {final_url}")
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

    print(f"\n  输出目录: {out}")
    print(f"  ├── task.json")
    print(f"  ├── result.json")
    print(f"  ├── analysis.json")
    print(f"  ├── screenshots/")
    print(f"  └── annotated/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()