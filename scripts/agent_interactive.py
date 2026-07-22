"""交互式 GUI Agent 入口：直接输入任务指令即可运行，无需写脚本。

增强功能 (基于 ShowUI 技术经验):
  --visual-grounder  启用视觉定位模块 (VisualGrounder)
  --decompose        启用任务分解 (VLM 自动拆分子任务)
  --visualize        生成标注截图 (预测点 + 框)
  --retry            失败后自动重试
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.env.selenium_web_env import SeleniumWebEnv
from gui_agent.executor.loop import AgentRunner
from gui_agent.grounding.keyword_grounder import KeywordGrounder
from gui_agent.llm.base import ChatMessage
from gui_agent.llm.factory import create_default_vlm


def main() -> None:
    parser = argparse.ArgumentParser(description="交互式 GUI Agent — 直接输入任务指令")
    parser.add_argument("--url", default="https://www.baidu.com", help="起始 URL (默认: 百度)")
    parser.add_argument("--task", default=None, help="任务描述（不传则交互式输入）")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge"], help="浏览器")
    parser.add_argument("--max-steps", type=int, default=10, help="最大步数")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--width", type=int, default=1280, help="窗口宽度")
    parser.add_argument("--height", type=int, default=800, help="窗口高度")

    # Phase 6: 增强功能参数
    parser.add_argument("--visual-grounder", action="store_true", help="启用视觉定位模块 (VisualGrounder)")
    parser.add_argument("--decompose", action="store_true", help="启用任务分解")
    parser.add_argument("--visualize", action="store_true", help="生成标注截图")
    parser.add_argument("--retry", action="store_true", help="失败后自动重试")
    parser.add_argument("--name", default=None, help="输出目录名（如 weather_xiamen_jimei）")
    args = parser.parse_args()

    # 如果没有传 task，交互式输入
    if args.task is None:
        print("=" * 60)
        print("  GUI Agent 交互式模式")
        if args.visual_grounder:
            print("  [增强] 视觉定位: 已启用")
        if args.decompose:
            print("  [增强] 任务分解: 已启用")
        if args.visualize:
            print("  [增强] 截图标注: 已启用")
        if args.retry:
            print("  [增强] 自动重试: 已启用")
        print("=" * 60)
        print(f"  起始 URL: {args.url}")
        print(f"  浏览器:   {args.browser}")
        print(f"  最大步数: {args.max_steps}")
        print("-" * 60)
        args.task = input("  请输入任务指令: ").strip()
        if not args.task:
            print("任务为空，退出。")
            return

    # 自动生成输出目录名
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    dir_name = args.name if args.name else f"interactive_{timestamp}"
    output_dir = ROOT / "outputs" / dir_name

    print(f"\n>> 启动 Agent...")
    print(f"  URL:      {args.url}")
    print(f"  任务:     {args.task}")
    print(f"  输出目录: {output_dir}")
    print("-" * 60)

    model = create_default_vlm()
    if model is None:
        print("未检测到 LLM/VLM 配置。请设置环境变量 GUIAGENT_LLM_BASE_URL / GUIAGENT_LLM_API_KEY / GUIAGENT_LLM_MODEL。")
        return

    from gui_agent.policy.llm_grounded import LLMGroundedPolicy

    # 可选: 任务分解
    if args.decompose:
        subtasks = _decompose_task(model, args.task, args.url)
        if subtasks:
            print(f"\n>> 任务分解为 {len(subtasks)} 个子任务:")
            for i, st in enumerate(subtasks, 1):
                print(f"    step {i}: {st}")
            # 用第一个子任务作为初始任务
            args.task = subtasks[0]

    # 构建 grounding 链
    grounder = KeywordGrounder()

    # 可选: VisualGrounder
    visual_grounder = None
    if args.visual_grounder and model is not None:
        from gui_agent.grounding.visual_grounder import VisualGrounder

        visual_grounder = VisualGrounder(vlm_model=model)
        print("  [OK] VisualGrounder 已加载")

    policy = LLMGroundedPolicy(
        grounder=grounder,
        visual_grounder=visual_grounder,
        model=model,
        use_vision=True,
        max_history=args.max_steps,
    )

    env = SeleniumWebEnv(
        start_url=args.url,
        task=args.task,
        output_dir=output_dir,
        window_size=(args.width, args.height),
        max_steps=args.max_steps,
        headless=args.headless,
        auto_submit_on_type=True,
        browser=args.browser,
        success_url_substring=_detect_success_url_hint(args.task, args.url),
        success_text=_detect_success_text_hint(args.task),
    )

    runner = AgentRunner(env=env, policy=policy, output_dir=output_dir, max_steps=args.max_steps)
    summary = runner.run()

    # 结果输出
    print("\n" + "=" * 60)
    print("  任务完成")
    print("=" * 60)
    print(f"  总步数:   {summary.get('total_steps', '?')}")
    print(f"  总奖励:   {summary.get('total_reward', '?')}")
    print(f"  是否成功: {summary.get('success', False)}")
    print(f"  截图目录: {output_dir / 'frames'}")
    print()

    # 显示增强评测指标
    grounding_acc = summary.get("grounding_accuracy", {})
    if grounding_acc:
        print("  Grounding 精度:")
        for action_type, stats in grounding_acc.items():
            print(f"    {action_type}: 命中 {stats.get('hit', 0)}/{stats.get('total', 0)} "
                  f"(准确率 {stats.get('accuracy', 0.0):.1%})")

    error_types = summary.get("error_types", {})
    if error_types and any(v > 0 for k, v in error_types.items() if k != "none"):
        print("  错误分类:")
        for err_type, count in error_types.items():
            if count > 0 and err_type != "none":
                print(f"    {err_type}: {count}")

    # 可选: 失败重试
    if args.retry and not summary.get("success"):
        print("\n[*] 任务失败，尝试重试（放宽参数）...")
        _retry_with_relaxed(args, model, output_dir)

    # 可选: 截图标注
    if args.visualize:
        _visualize_all_steps(output_dir)

    print("=" * 60)


def _decompose_task(model, task: str, url: str) -> list[str]:
    """Use VLM to break a complex task into sequential subtasks."""
    prompt = (
        "You are a task planner for a GUI automation agent. "
        f"Given the starting URL '{url}', break this task into 2-5 sequential subtasks:\n"
        f"TASK: {task}\n\n"
        "Output a JSON array of strings, each describing one subtask step.\n"
        "Example: [\"Search for 'artificial intelligence'\", \"Click the first result\"]\n"
        "Return JSON only."
    )
    try:
        resp = model.chat([ChatMessage(role="user", content=prompt)])
        # Parse JSON array
        text = resp.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("\n", 1)[0] if "\n" in text else text
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        subtasks = json.loads(text)
        if isinstance(subtasks, list) and all(isinstance(s, str) for s in subtasks):
            return subtasks
    except Exception:
        pass
    return []


def _visualize_all_steps(output_dir: Path) -> None:
    """Draw predicted click points on all step screenshots."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  [skip] 请安装 Pillow 以启用截图标注: pip install Pillow")
        return

    viz_dir = output_dir / "viz"
    viz_dir.mkdir(parents=True, exist_ok=True)

    steps_path = output_dir / "steps.jsonl"
    if not steps_path.exists():
        return

    import json as _json

    with steps_path.open(encoding="utf-8") as fh:
        for line in fh:
            record = _json.loads(line)
            step_id = record.get("step_id", "?")
            grounding = record.get("grounding") or {}
            action = record.get("action") or {}
            obs = record.get("observation") or {}
            screenshot_path = obs.get("screenshot_path", "")

            if not screenshot_path or not Path(screenshot_path).exists():
                continue

            point = grounding.get("point")
            bbox = grounding.get("bbox")
            if point is None and bbox is None:
                continue

            try:
                img = Image.open(screenshot_path).convert("RGB")
                draw = ImageDraw.Draw(img)
                w, h = img.size

                if point:
                    px, py = int(point[0] * w), int(point[1] * h)
                    r = 6
                    draw.ellipse([px - r, py - r, px + r, py + r], fill="red", outline="white")
                    # Label
                    label = action.get("action", "?")
                    draw.text((px + r + 4, py - 8), label, fill="red")

                if bbox:
                    x1, y1, x2, y2 = (
                        int(bbox[0] * w),
                        int(bbox[1] * h),
                        int(bbox[2] * w),
                        int(bbox[3] * h),
                    )
                    draw.rectangle([x1, y1, x2, y2], outline="lime", width=3)

                output_viz_path = str(viz_dir / f"step_{step_id}.png")
                img.save(output_viz_path)
                print(f"  [viz] step {step_id}: {output_viz_path}")
            except Exception as exc:
                print(f"  [viz] step {step_id} error: {exc}")


def _retry_with_relaxed(args, model, output_dir: Path) -> None:
    """Retry with relaxed parameters (more steps, non-headless)."""
    from gui_agent.grounding.visual_grounder import VisualGrounder
    from gui_agent.policy.llm_grounded import LLMGroundedPolicy

    retry_dir = output_dir / "retry"

    visual_grounder = None
    if args.visual_grounder:
        visual_grounder = VisualGrounder(vlm_model=model)

    env = SeleniumWebEnv(
        start_url=args.url,
        task=args.task,
        output_dir=retry_dir,
        window_size=(args.width, args.height),
        max_steps=args.max_steps * 2,
        headless=False,
        auto_submit_on_type=True,
        browser=args.browser,
    )

    policy = LLMGroundedPolicy(
        grounder=KeywordGrounder(),
        visual_grounder=visual_grounder,
        model=model,
        use_vision=True,
        max_history=args.max_steps * 2,
    )

    runner = AgentRunner(env=env, policy=policy, output_dir=retry_dir, max_steps=args.max_steps * 2)
    summary = runner.run()

    print(f"  重试结果: 成功={summary.get('success', False)} "
          f"步数={summary.get('total_steps', '?')} "
          f"奖励={summary.get('total_reward', '?')}")


# ── 成功检测自动推断 ──


def _detect_success_url_hint(task: str, start_url: str) -> str | None:
    """从任务描述和起始 URL 中推断 success_url_substring 的值。

    策略：
    1. 如果任务包含引号括起来的内容（如 '厦门'、"Xiamen"），用引号内容
    2. 如果起始 URL 是搜索引擎首页，用任务中的第一个有意义的搜索关键词
    """
    import re

    # 1. 引号中的内容
    quoted = re.findall(r"['\"“”]([^'\"“”]{2,})['\"“”]", task)
    if quoted:
        # 取最长的引号内容作为成功检测词
        return max(quoted, key=len)

    # 2. 从任务中提取有意义的实词（中文或英文名词）
    words = re.findall(r"[A-Za-z]\w{2,}", task)
    for w in words:
        if w.lower() not in ("com", "http", "https", "www", "the", "and", "for"):
            return w

    return None


def _detect_success_text_hint(task: str) -> str | None:
    """从任务中提取 success_text 关键词。

    提取中文关键词（2汉字以上）中最长的作为页面内容检测词。
    """
    import re

    # 提取中文句子中的中文词（2个以上汉字）
    chinese_words = re.findall(r"[一-鿿]{2,}", task)
    if chinese_words:
        # 排除常见非内容词
        stop_words = {"搜索", "输入", "点击", "打开", "查看", "进入", "找到", "结果", "页面", "然后"}
        meaningful = [w for w in chinese_words if w not in stop_words and len(w) >= 2]
        if meaningful:
            return max(meaningful, key=len)
        # 如果没有"有意义"的词，用最长的词
        return max(chinese_words, key=len)
    return None


if __name__ == "__main__":
    main()
