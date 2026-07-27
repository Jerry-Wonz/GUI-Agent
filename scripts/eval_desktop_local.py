"""Desktop 应用评测 — 本地 HTML 桌面模拟器 + 真实桌面交互。

任务：打开一个本地桌面模拟器应用（HTML），完成以下操作：
1. 在任务管理器中添加一个新任务
2. 设置任务的优先级
3. 标记任务为完成
4. 验证任务列表更新

这模拟了 Desktop GUI Agent 在真实桌面应用中的操作流程。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / f"desktop_local_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 创建一个本地桌面模拟器 HTML 文件
DESKTOP_APP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Task Manager - Desktop App</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Arial, sans-serif; }
body { background: #2d2d2d; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.window {
    width: 800px; height: 600px; background: #f0f0f0; border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3); overflow: hidden;
    display: flex; flex-direction: column;
}
.titlebar {
    background: #e8e8e8; padding: 8px 16px; display: flex;
    align-items: center; gap: 8px; border-bottom: 1px solid #ccc;
    cursor: default; user-select: none;
}
.titlebar .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.titlebar .close { background: #ff5f57; }
.titlebar .min { background: #febc2e; }
.titlebar .max { background: #28c840; }
.titlebar .title { flex: 1; text-align: center; font-size: 13px; color: #333; }
.toolbar { background: #fafafa; padding: 8px; border-bottom: 1px solid #ddd; display: flex; gap: 6px; }
.toolbar button {
    padding: 6px 14px; border: 1px solid #ccc; background: #fff; border-radius: 4px;
    cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 4px;
}
.toolbar button:hover { background: #e8e8e8; }
.toolbar button.primary { background: #0078d4; color: #fff; border-color: #0078d4; }
.toolbar button.primary:hover { background: #106ebe; }
.content { flex: 1; display: flex; }
.sidebar { width: 180px; background: #f5f5f5; border-right: 1px solid #ddd; padding: 8px; }
.sidebar .item {
    padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; margin-bottom: 2px;
}
.sidebar .item:hover { background: #e0e0e0; }
.sidebar .item.active { background: #0078d4; color: #fff; }
.sidebar .item .icon { margin-right: 8px; }
.main { flex: 1; padding: 16px; overflow-y: auto; }
.list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.list-header h2 { font-size: 18px; color: #333; }
.task-item {
    display: flex; align-items: center; padding: 10px 12px; border: 1px solid #e0e0e0;
    border-radius: 6px; margin-bottom: 6px; background: #fff; gap: 10px;
}
.task-item:hover { border-color: #0078d4; }
.task-item .check {
    width: 18px; height: 18px; border: 2px solid #ccc; border-radius: 3px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-size: 12px; color: #fff; flex-shrink: 0;
}
.task-item .check.done { background: #0078d4; border-color: #0078d4; }
.task-item .info { flex: 1; }
.task-item .title-text { font-size: 14px; color: #333; }
.task-item .title-text.done-text { text-decoration: line-through; color: #999; }
.task-item .desc { font-size: 11px; color: #888; }
.task-item .priority { font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: bold; }
.priority-high { background: #ffebee; color: #c62828; }
.priority-medium { background: #fff8e1; color: #f57f17; }
.priority-low { background: #e8f5e9; color: #2e7d32; }
.modal-overlay {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4); z-index: 1000;
    justify-content: center; align-items: center;
}
.modal-overlay.active { display: flex; }
.modal {
    background: #fff; border-radius: 8px; padding: 24px; width: 420px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.modal h3 { margin-bottom: 16px; font-size: 16px; color: #333; }
.modal label { display: block; font-size: 12px; color: #555; margin-bottom: 4px; }
.modal input, .modal select, .modal textarea {
    width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;
    margin-bottom: 12px; font-size: 13px;
}
.modal textarea { height: 60px; resize: vertical; }
.modal .btn-row { display: flex; gap: 8px; justify-content: flex-end; }
.modal .btn-row button { padding: 8px 20px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.modal .btn-cancel { border: 1px solid #ccc; background: #fff; }
.modal .btn-save { border: none; background: #0078d4; color: #fff; }
#statusbar {
    background: #0078d4; color: #fff; padding: 4px 16px; font-size: 11px;
    display: flex; justify-content: space-between;
}
</style>
</head>
<body>
<div class="window" id="app">
    <div class="titlebar">
        <span class="dot close"></span><span class="dot min"></span><span class="dot max"></span>
        <span class="title">Task Manager</span>
    </div>
    <div class="toolbar">
        <button class="primary" id="btnNewTask">+ New Task</button>
        <button id="btnRefresh">↻ Refresh</button>
        <button id="btnDelete">🗑 Delete</button>
    </div>
    <div class="content">
        <div class="sidebar">
            <div class="item active" data-filter="all"><span class="icon">📋</span> All Tasks</div>
            <div class="item" data-filter="today"><span class="icon">📅</span> Today</div>
            <div class="item" data-filter="high"><span class="icon">🔴</span> High Priority</div>
            <div class="item" data-filter="done"><span class="icon">✅</span> Completed</div>
        </div>
        <div class="main" id="taskList">
            <div class="list-header">
                <h2>All Tasks</h2>
                <span style="font-size:12px;color:#888;" id="taskCount">3 tasks</span>
            </div>
        </div>
    </div>
    <div id="statusbar"><span>Ready</span><span id="clock"></span></div>
</div>

<div class="modal-overlay" id="modalOverlay">
    <div class="modal">
        <h3>New Task</h3>
        <label>Title</label>
        <input type="text" id="inputTitle" placeholder="Enter task title...">
        <label>Description</label>
        <textarea id="inputDesc" placeholder="Enter description..."></textarea>
        <label>Priority</label>
        <select id="inputPriority">
            <option value="low">Low</option>
            <option value="medium" selected>Medium</option>
            <option value="high">High</option>
        </select>
        <div class="btn-row">
            <button class="btn-cancel" id="btnCancel">Cancel</button>
            <button class="btn-save" id="btnSave">Save Task</button>
        </div>
    </div>
</div>

<script>
let tasks = [
    { id: 1, title: 'Review project proposal', desc: 'Check the Q3 roadmap', priority: 'high', done: false },
    { id: 2, title: 'Update documentation', desc: 'Add API references', priority: 'medium', done: false },
    { id: 3, title: 'Team standup notes', desc: 'Prepare meeting agenda', priority: 'low', done: false },
];
let nextId = 4;
let currentFilter = 'all';

function render() {
    const list = document.getElementById('taskList');
    const header = list.querySelector('.list-header h2');
    const filtered = tasks.filter(t => {
        if (currentFilter === 'done') return t.done;
        if (currentFilter === 'high') return t.priority === 'high' && !t.done;
        if (currentFilter === 'today') return !t.done;
        return true;
    });
    const count = filtered.length;
    document.getElementById('taskCount').textContent = count + ' task' + (count !== 1 ? 's' : '');
    header.textContent = currentFilter === 'all' ? 'All Tasks' :
                         currentFilter === 'done' ? 'Completed' :
                         currentFilter === 'high' ? 'High Priority' : 'Today';
    const items = list.querySelectorAll('.task-item');
    items.forEach(el => el.remove());
    filtered.forEach(t => {
        const div = document.createElement('div');
        div.className = 'task-item';
        div.innerHTML = `
            <div class="check ${t.done ? 'done' : ''}" data-id="${t.id}">${t.done ? '✓' : ''}</div>
            <div class="info">
                <div class="title-text ${t.done ? 'done-text' : ''}">${t.title}</div>
                <div class="desc">${t.desc}</div>
            </div>
            <span class="priority priority-${t.priority}">${t.priority}</span>
        `;
        div.querySelector('.check').onclick = function() {
            t.done = !t.done;
            render();
            updateStatus('Task "' + t.title + '" ' + (t.done ? 'completed' : 'reopened'));
        };
        list.appendChild(div);
    });
}
function updateStatus(msg) {
    document.getElementById('statusbar').children[0].textContent = msg;
}
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toLocaleTimeString();
}
document.querySelectorAll('.sidebar .item').forEach(el => {
    el.onclick = function() {
        document.querySelectorAll('.sidebar .item').forEach(e => e.classList.remove('active'));
        this.classList.add('active');
        currentFilter = this.dataset.filter;
        render();
        updateStatus('Filter: ' + this.textContent.trim());
    };
});
document.getElementById('btnNewTask').onclick = function() {
    document.getElementById('inputTitle').value = '';
    document.getElementById('inputDesc').value = '';
    document.getElementById('inputPriority').value = 'medium';
    document.getElementById('modalOverlay').classList.add('active');
    document.getElementById('inputTitle').focus();
};
document.getElementById('btnCancel').onclick = function() {
    document.getElementById('modalOverlay').classList.remove('active');
};
document.getElementById('btnSave').onclick = function() {
    const title = document.getElementById('inputTitle').value.trim();
    if (!title) { alert('Please enter a title'); return; }
    tasks.push({
        id: nextId++,
        title: title,
        desc: document.getElementById('inputDesc').value.trim() || 'No description',
        priority: document.getElementById('inputPriority').value,
        done: false,
    });
    document.getElementById('modalOverlay').classList.remove('active');
    render();
    updateStatus('Task "' + title + '" created');
};
document.getElementById('btnRefresh').onclick = function() { render(); updateStatus('Refreshed'); };
document.getElementById('btnDelete').onclick = function() {
    const doneTasks = tasks.filter(t => t.done);
    if (doneTasks.length === 0) { alert('No completed tasks to delete'); return; }
    tasks = tasks.filter(t => !t.done);
    render();
    updateStatus(doneTasks.length + ' completed task(s) deleted');
};
document.getElementById('modalOverlay').onclick = function(e) { if (e.target === this) this.classList.remove('active'); };
updateClock();
setInterval(updateClock, 1000);
render();
updateStatus('Ready - ' + tasks.length + ' tasks loaded');
</script>
</body>
</html>
"""


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

    # 写入本地桌面应用 HTML
    html_path = str(out / "desktop_app.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(DESKTOP_APP_HTML)

    print("加载 ShowUI-2B...")
    grounder = ShowUIGrounder(mode="navigation")

    print("打开本地桌面模拟器...")
    options = webdriver.ChromeOptions()
    ws = (1280, 900)
    options.add_argument(f"--window-size={ws[0]},{ws[1]}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(ws[0], ws[1])
    driver.get("file://" + html_path)
    time.sleep(2)

    task = (
        "Use the Task Manager desktop application. "
        "First, click the '+ New Task' button to create a new task. "
        "In the dialog, enter 'Prepare quarterly report' as the title, "
        "set priority to 'High', and click 'Save Task'. "
        "Then, mark the first task 'Review project proposal' as completed by clicking its checkbox. "
        "Finally, click on 'Completed' in the sidebar to show only completed tasks."
    )

    history: list[dict] = []
    steps: list[dict] = []
    task_completed = False
    max_steps = 10

    print(f"\n{'='*60}")
    print(f"  任务: Desktop 任务管理器操作")
    print(f"  最大步数: {max_steps}")
    print(f"{'='*60}\n")

    for step_idx in range(1, max_steps + 1):
        print(f"\n--- Step {step_idx} ---")

        screenshot_path = str(screenshots_dir / f"step_{step_idx}.png")
        driver.save_screenshot(screenshot_path)

        # 检查是否完成任务
        try:
            body_text = driver.find_element("tag name", "body").text
            # 检查是否已创建新任务并标记完成
            if "Prepare quarterly report" in body_text:
                try:
                    items = driver.find_elements(By.CLASS_NAME, "task-item")
                    for item in items:
                        title_el = item.find_element(By.CLASS_NAME, "title-text")
                        if "Review project proposal" in title_el.text:
                            classes = title_el.get_attribute("class")
                            if "done-text" in classes:
                                print(f"  ✅ 任务完成！新任务已创建，Review project proposal 已标记完成")
                                task_completed = True
                                break
                except Exception:
                    pass
            if task_completed:
                break
        except Exception:
            pass

        try:
            result = grounder.predict_action(
                screenshot_path=screenshot_path,
                task=task,
                device_type="web",
                history=history,
            )
        except Exception as e:
            print(f"  ❌ ShowUI 预测失败: {e}")
            steps.append({"step": step_idx, "action": "ERROR", "error": str(e)})
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
                time.sleep(1.5)

            elif action_type == "SCROLL":
                direction = value or "down"
                scroll_y = 300 if direction == "down" else -300
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

        step_record = {
            "step": step_idx,
            "action": action_type,
            "value": value,
            "predicted_position": position,
            "action_success": action_success,
            "action_error": action_error,
        }
        steps.append(step_record)

        history.append({
            "action": action_type,
            "value": value,
            "position": position,
        })

        # 标注截图
        annotated_path = str(annotated_dir / f"step_{step_idx}.png")
        pred_point = (position[0], position[1]) if position and len(position) == 2 else None
        annotate_screenshot(
            screenshot_path, annotated_path, step_idx,
            action=result, predicted_point=pred_point, window_size=ws,
        )

    # 最终截图
    driver.save_screenshot(str(screenshots_dir / "final.png"))
    if task_completed:
        Image.open(str(screenshots_dir / "final.png")).convert("RGB").save(str(annotated_dir / "final.png"))

    driver.quit()

    # 保存结果
    task_info = {
        "task": "Desktop Task Manager 操作",
        "description": "本地 HTML 桌面模拟器，模拟真实桌面应用交互",
        "app": "Task Manager (HTML Desktop Simulator)",
        "max_steps": max_steps,
        "timestamp": datetime.now().isoformat(),
    }
    with open(out / "task.json", "w", encoding="utf-8") as f:
        json.dump(task_info, f, indent=2, ensure_ascii=False)

    result = {
        "task": "Desktop Task Manager 操作",
        "completed": task_completed,
        "total_steps": len(steps),
        "steps": steps,
    }
    with open(out / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # 分析报告
    analysis = {
        "task": "Desktop Task Manager 操作",
        "completed": task_completed,
        "total_steps": len(steps),
        "successful_actions": sum(1 for s in steps if s["action_success"]),
        "failed_actions": sum(1 for s in steps if not s["action_success"]),
        "capabilities": {
            "visual_understanding": "理解桌面应用布局（标题栏、工具栏、侧边栏、内容区）",
            "target_localization": "定位按钮、文本框、下拉菜单、复选框等控件",
            "action_planning": "规划多步操作序列（点击 → 输入 → 保存 → 切换视图）",
            "form_interaction": "填写表单、选择下拉选项、提交数据",
        },
    }
    with open(out / "analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    # 输出报告
    print(f"\n{'='*60}")
    print(f"  Desktop 应用评测报告")
    print(f"{'='*60}")
    print(f"  应用: Task Manager (本地桌面模拟器)")
    print(f"  完成状态: {'✅ 成功' if task_completed else '❌ 失败'}")
    print(f"  总步数: {len(steps)}")
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
    print(f"  ├── desktop_app.html (本地桌面模拟器)")
    print(f"  ├── task.json")
    print(f"  ├── result.json")
    print(f"  ├── analysis.json")
    print(f"  ├── screenshots/")
    print(f"  └── annotated/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()