# GUI Agent — 面向网页操作的视觉智能体实践报告

> **项目定位**：面向研究生入门的低算力 GUI Grounding + Web Agent 实践项目  
> **技术参考**：ShowUI: One Vision-Language-Action Model for GUI Visual Agent (CVPR 2025)  
> **报告日期**：2026-07-19  
> **运行环境**：Windows 11, Chrome 150, VLM: GLM-4.6V (智谱)

---

## 1. 项目背景

### 1.1 GUI Agent 的研究价值

近两年多模态智能体研究中，一个明确的方向是让模型不仅能"看懂界面"，还能"基于界面执行动作"。相比具身机器人、3D 仿真等方向，GUI Agent 具备更低的工程门槛和更清晰的实验闭环，非常适合作为入门型实践项目。

GUI Agent 通常拆成两个相互衔接的问题：

1. **GUI Grounding**：给定截图和文本指令，定位目标控件或可交互区域
2. **Web Agent**：给定任务目标、网页观察和历史动作，预测下一步操作

### 1.2 ShowUI 的技术启发

本项目的设计深受 **ShowUI**（CVPR 2025, Show Lab NUS & Microsoft）的启发。ShowUI 是一个基于 Qwen2-VL-2B 的轻量视觉-语言-动作（VLA）模型，仅用 256K 训练数据就在 ScreenSpot 上达到 75.1% 的零样本定位精度。

ShowUI 的三个核心创新：

| 创新点 | 技术方案 | 对本项目启发 |
|--------|---------|-------------|
| **UI-Guided Visual Token Selection** | 利用 UI 截图的结构性冗余（Union-Find 连通组件），33% Token 压缩 | 纯视觉定位的可行性 |
| **Interleaved VLA Streaming** | 历史截图与动作交错输入，保持多步上下文 | 历史记忆的重要性 |
| **小数据高精度** | 256K 精选数据 + 重平衡采样 | 低算力路线的可行性 |

与 ShowUI 训练端到端模型不同，本项目采用 **API 编排路线**，用已有 VLM API 搭建一个能做 GUI 任务的系统，无需 GPU 训练即可快速验证 GUI Agent 的核心闭环，适合低算力环境下的研究和学习。

---

## 2. 系统架构

### 2.1 整体架构

系统采用**六层模块化设计**，各层职责清晰、可独立替换：

```
┌─────────────────────────────────────────────────────────┐
│                    AgentRunner (执行循环)                  │
│  ┌──────┐  ┌──────────┐  ┌──────┐  ┌────────┐  ┌──────┐  │
│  │ Env  │→ │Observation│→ │Policy│→ │Executor│→ │Eval  │  │
│  │ 环境  │  │  观察处理  │  │ 策略  │  │ 执行器  │  │ 评测  │  │
│  └──────┘  └──────────┘  └──────┘  └────────┘  └──────┘  │
│                                  ↕                        │
│                            ┌──────────┐                  │
│                            │ Grounding │                  │
│                            │  定位模块  │                  │
│                            └──────────┘                  │
│                                  ↕                        │
│                            ┌──────────┐                  │
│                            │  Memory   │                  │
│                            │  记忆模块  │                  │
│                            └──────────┘                  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 模块说明

| 模块 | 职责 | 实现 |
|------|------|------|
| **Env** | 网页环境交互 | MockWebEnv, MiniWoBEnv, SeleniumWebEnv |
| **Observation** | 将环境状态转为结构化输入 | 截图路径 + DOM 元素 + 历史动作 |
| **Grounding** | 文本目标 → 界面坐标映射 | KeywordGrounder / VisualGrounder |
| **Policy** | 根据观察生成下一步动作 | RuleBased / MiniWoBRule / LLMGrounded |
| **Executor** | 动作执行与失败恢复 | AgentRunner 主循环 |
| **Evaluation** | 指标统计与错误分类 | 增强版评测指标 |
| **Memory** | 跨步骤状态追踪 | TaskMemory 上下文注入 |

### 2.3 数据流

每步执行的数据流：

```
1. Env.reset() → Observation
2. TaskMemory 注入上下文 → Observation.metadata
3. Policy.act(Observation) → Action
   ├─ 3a. 调用 VLM，输出 JSON 动作意图
   ├─ 3b. Grounding 三级降级链 → 坐标
   └─ 3c. 组装最终 Action
4. Env.step(Action) → (next_obs, reward, terminated, info)
5. 记录 StepRecord → steps.jsonl
6. TaskMemory.record() 记录本步结果
7. 如果未终止，回到步骤 1
```

---

## 3. 技术方案

### 3.1 三级降级 Grounding 链

这是本项目的核心设计，借鉴了 ShowUI 的端到端坐标输出思路，同时保留了 DOM 文本匹配作为兜底：

```
Level 1: VLM 直接输出 position [x, y]        ← 最高优先级，端到端
   ↓ 若无 position 或坐标无效
Level 2: VisualGrounder（截图 → VLM → 坐标）   ← 纯视觉定位
   ↓ 若无 visual_grounder 或置信度不足
Level 3: KeywordGrounder（DOM 文本关键词匹配）   ← 兜底方案
```

**Level 1 — VLM Direct**：VLM 在输出动作 JSON 时直接附带 `position: [x, y]`（归一化坐标 0-1）。如果 VLM 错误输出了像素坐标，系统自动检测并归一化。

**Level 2 — VisualGrounder**：一个独立的视觉定位模块，实现 `BaseGrounder` 接口。向 VLM 发送专用 prompt，要求输出目标元素的归一化坐标和置信度。如果提供了 DOM 元素列表，还会做一致性校验——预测点是否落在某个元素框内，据此调整置信度。

**Level 3 — KeywordGrounder**：原始 grounding 方案，通过元素文本关键词匹配 + 语义类型提示（如"搜索框"→ `<input>`）来定位。不需要调用 VLM，速度最快。

### 3.2 视觉历史记忆

对应 ShowUI 的 Interleaved VLA Streaming：

- 每步的 `history` 条目增加了 `screenshot_path` 字段
- VLM prompt 中可传入**多张历史截图**（由 `visual_history_count` 参数控制）
- `BaseVisionChatModel` 新增 `chat_with_images()` 接口，OpenAI 和智谱 API 均已支持多图调用

### 3.3 TaskMemory 任务记忆

轻量级记忆模块，在 AgentRunner 循环中自动运行：

- 记录每步的 action_type、target_text、grounding_score、reward、error
- `get_progress_summary()` → 生成最近 3 步的进展文本，注入 VLM prompt
- `get_grounding_patterns()` → 统计哪种 grounding 方式平均置信度最高

### 3.4 增强评测指标

在原有的 `total_steps` / `total_reward` / `success` 基础上增加了：

- **grounding_accuracy_per_action**：按动作类型统计定位命中率
- **error_classification**：将错误分为 perception/grounding/decision/execution 四类
- **vlm_response_quality**：VLM 的 JSON 解析成功率

---

## 4. 实验测评

### 4.1 案例一：Wikipedia 搜索 "Artificial intelligence"

这是项目最早验证成功的场景，展示了最基础的 VLM Agent 闭环。

**配置**：

- 起始页：`https://en.wikipedia.org/wiki/Main_Page`
- 任务：`Search for 'Artificial intelligence' in the search box`
- 成功条件：URL 包含 `Artificial_intelligence`
- VLM：GLM-4.6V（智谱），视觉模式

**执行过程**：

| 步骤 | 动作 | 说明 |
|:----:|:----|:-----|
| reset | 加载 Wikipedia 首页 | 展示搜索框和导航栏 |
| Step 0 | CLICK 搜索框 | VLM 定位到页面右上角的搜索输入框 |
| Step 1 | TYPE "Artificial intelligence" + Enter | 输入搜索词，自动提交，页面跳转到 AI 词条 |
| 完成 | reward=1.0, success=True | URL 命中 `Artificial_intelligence` |

**执行截图**：

> `outputs/real_web_vlm/frames/`
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\real_web_vlm\frames\reset.png)
>
> - `reset.png` — Wikipedia 首页
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\real_web_vlm\frames\step_1.png)
>
> - `step_1.png` — 输入搜索词后的页面
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\real_web_vlm\frames\step_2.png)
>
> - `step_2.png` — 搜索结果页（Artificial intelligence 词条）

**结果 summary**：

```json
{ "total_steps": 2, "total_reward": 1.0, "success": true }
```

---

### 4.2 案例二：Google Maps 搜索厦门

这是项目改进后的完整测试，验证了三级降级链、视觉历史记忆和增强评测的全部能力。

**配置**：
- 起始页：`https://www.google.com/maps`
- 任务：`在谷歌地图的搜索框中输入 '厦门' 然后按回车查看搜索结果`
- VLM：GLM-4.6V（智谱），视觉模式
- 启用：VisualGrounder + 可视化标注 + 增强评测

**执行过程**：

| 步骤 | 动作 | 坐标(归一化) | 页面状态 | Grounding |
|:----:|:----|:-----------:|:---------|:---------:|
| reset | — | — | Google Maps 首页加载完成 | — |
| Step 0 | CLICK 搜索框 | [0.122, 0.073] | 搜索框获得焦点 | vlm_direct (1.0) |
| Step 1 | TYPE "厦门" + Enter | [0.127, 0.073] | 跳转到厦门 Place 页 | vlm_direct (1.0) |

**URL 变化**：
```
Step 0: https://www.google.com/maps
Step 1: https://www.google.com/maps/place/中国福建省厦门市/...
```

从首页到厦门市 Place 页面的完整导航，仅 2 步完成。

**执行截图**：

> `outputs/interactive_20260719_155612/frames/`
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\interactive_20260719_154310\frames\reset.png)
>
> - `reset.png` — Google Maps 首页（1280×800）
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\interactive_20260719_154310\frames\step_1.png)
>
> - `step_1.png` — 输入"厦门"后页面状态
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\interactive_20260719_154310\frames\step_3.png)
>
> - `step_2.png` — 厦门 Place 页（搜索结果）

> `outputs/interactive_20260719_155612/viz/`（标注截图）
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\interactive_20260719_155612\viz\step_0.png)
>
> - `step_0.png` — 红色圆点标注了 VLM 预测的 CLICK 坐标 [0.122, 0.073]
>
> ![](D:\05 WorkSpace\GUIAgent\outputs\interactive_20260719_155612\viz\step_1.png)
>
> - `step_1.png` — 红色圆点标注了 TYPE 坐标 [0.127, 0.073]

**增强评测结果**：
```json
{
  "total_steps": 2,
  "total_reward": 1.0,
  "success": true,
  "grounding_accuracy": {
    "CLICK": { "total": 1, "hit": 1, "accuracy": 1.0, "sources": {"vlm_direct": 1} },
    "TYPE":  { "total": 1, "hit": 1, "accuracy": 1.0, "sources": {"vlm_direct": 1} }
  },
  "error_types": {
    "perception": 0, "grounding": 0, "decision": 0, "execution": 0, "none": 2
  },
  "vlm_quality": {
    "total_calls": 2, "valid_json": 2, "valid_json_rate": 1.0
  }
}
```

**要点分析**：
- 所有动作的 grounding 来源均为 `vlm_direct`（VLM 直接输出坐标），说明三级降级链的 Level 1 工作稳定

- 零执行错误（execution=0），CLICK 和 TYPE 全部命中目标

- 自动归一化检测生效——VLM 输出了像素坐标 [156, 58]，系统自动除以窗口尺寸转为 [0.122, 0.073]

- `success_url_substring` 自动从任务中的引号内容"厦门"提取，成功匹配解码后的 URL

  

---

## 5. 局限与未来工作

### 5.1 失败案例一：天气网站元素定位失败

**场景**：`tianqi.com` — 查看厦门市集美区的风速  
**失败模式**：VLM 在首页 `[0.40, 0.15]` 处点击了非输入元素（可能是城市链接或标题），后续 7 次 TYPE 全部因 `invalid element state` 失败。

```
Step 0: CLICK at [0.40, 0.15]    → 点到了 <div>/<a> 而非 <input>
Step 1: TYPE "厦门市集美区"        → ERROR: invalid element state
Step 2-9: 连续重试同一动作 ×7     → 全部失败
```

**根因分析**：
- VLM 误将页面上的城市名称元素识别为搜索框（视觉特征相似）
- 点击后焦点落在一个不可编辑元素上，后续 TYPE 无法执行
- VLM 缺乏"从反复错误中切换策略"的能力——相同的错误连续发生 7 次，VLM 仍输出同一动作

**改进方向**：
- 在执行器中加入"连续相同错误 → 强制换策略"的规则
- TYPE 动作前增加元素类型校验（`get_clicked_element_tag()` 已添加，待进一步集成）

### 5.2 失败案例二：MSN 天气地区选择器

**场景**：`msn.com/zh-tw/weather` — 查询集美区的风速  
**失败模式**：MSN 天气页面使用复杂的位置选择 UI（地区选择器 + 位置参数），而非简单的搜索输入框。VLM 无法理解这种交互模式。

```
Step 0: CLICK    → 触发地区选择
Step 1-3: CLICK  → 在葵青區（香港）选项中循环
Step 4: TYPE     → 输入"厦门市集美区"但页面不接受
Step 5-7: 继续 CLICK 循环
```

**根因分析**：
- MSN 天气的"切换城市"功能通过一个视觉上不明显的地区选择器实现，VLM 难以识别
- 页面根据 IP 自动重定向到香港版（`zh-hk`），增加了交互复杂度
- 网站特有的 UI 模式（非标准搜索框）是纯视觉 VLM 的天然弱点

**改进方向**：
- 对复杂交互网站，改用**直接 URL 导航**策略（如直接构造天气城市 URL）
- 在 TaskMemory 中加入"页面结构识别"——如果同一种交互模式失败多次，尝试 URL 直跳

### 5.3 当前局限性总结

| 局限 | 描述 |
|:----|:-----|
| **VLM 策略适应能力弱** | 连续失败后仍重复相同动作 |
| **网站特有 UI 识别困难** | 非标准交互组件（地区选择器等）无法处理 |
| **无批量评测** | 未在 ScreenSpot / MiniWoB++ 等标准化数据集上跑批量指标 |
| **视觉定位精度未量化** | VisualGrounder 仅在有限场景测试，缺乏 ScreenSpot 基准成绩 |
| **无多图历史验证** | `chat_with_images()` 已完成但未在实际任务中启用 |

### 5.4 未来工作方向

1. **执行器智能降级**：出现连续 N 次相同错误自动切换策略
2. **ScreenSpot 批量评测**：调用 VisualGrounder 在标准 grounding 数据集上跑基准成绩
3. **DOM + 视觉融合 Grounding**：将 DOM 结构信息作为 VLM 的辅助输入，提高非标准 UI 的识别率

4. **Multi-step Planner**：在 Policy 层增加独立的子任务分解模块，支持长程任务自动拆解
4. **小模型微调**：在自建数据集上用 LoRA 微调 2B 级 VLM，验证"低算力训练路线"的可行性

6. **Desktop Agent 扩展**：将框架扩展到桌面操作系统操作
