# GUIAgent

一个面向 `GUI Grounding + Web Agent` 小项目的最小工程骨架。

当前版本目标不是直接提供完整 benchmark 结果，而是先建立一个可运行、可扩展、可记录日志的项目基础设施，支持后续接入：

- Mock Web 环境
- GUI grounding baseline
- Rule-based policy
- Agent loop
- MiniWoB++ 真实 benchmark 适配
- BrowserGym 扩展接口

## 目录说明

```text
GUIAgent/
├─ configs/
├─ docs/
├─ scripts/
├─ src/
│  └─ gui_agent/
└─ outputs/
```

## 快速开始

### 0. 安装依赖

```bash
python -m pip install -r requirements.txt
```

当前真实 benchmark / 真实网页 路线依赖：

- `gymnasium`
- `miniwob`
- `selenium`
- `webdriver-manager`

### 0.1 使用项目独立虚拟环境（推荐）

创建虚拟环境：

```bash
python -m venv .venv
```

激活（PowerShell）：

```bash
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 1. 运行 grounding demo

```bash
python scripts/run_grounding_demo.py
```

### 2. 运行 mock agent demo

```bash
python scripts/run_mock_agent.py
```

### 3. 运行 MiniWoB++ click benchmark demo

```bash
python scripts/run_miniwob_click.py
```

当前实现会自动尝试：

- 发现本机 Chrome / Edge 路径
- 使用 `webdriver-manager` 准备 `chromedriver`
- 将截图保存到 `outputs/miniwob_click/frames/`

如果环境缺失，脚本会给出明确错误提示。

运行后会在 `outputs/` 下生成日志与汇总结果。

### 4. 运行 LLM/VLM 版本

- `scripts/run_miniwob_click_llm.py`
  - 文本路线，主要利用任务文本和结构化元素信息
- `scripts/run_miniwob_click_vlm.py`
  - 视觉路线，模型直接查看屏幕截图后输出 GUI 动作，再由 grounding 映射到元素或坐标
  - 默认将 MiniWoB 单轮超时放宽到 `30000ms`，避免远程 VLM 请求被 benchmark 默认 `10s` 计时直接打断

先配置环境变量（OpenAI-compatible 或厂商原生 HTTP 接口都可）：

```bash
setx GUIAGENT_LLM_BASE_URL "https://open.bigmodel.cn/api/paas/v4"
setx GUIAGENT_LLM_API_KEY "your-api-key"
setx GUIAGENT_LLM_MODEL "glm-5v-turbo"
```

如果使用的是智谱原生 `paas/v4`（如上示例），建议再设置：

```bash
setx GUIAGENT_LLM_PROVIDER "zhipu"
```

然后运行：

```bash
python scripts/run_miniwob_click_llm.py
python scripts/run_miniwob_click_vlm.py
```

说明：

- `glm-5v-turbo` 支持图文输入，适合 `run_miniwob_click_vlm.py`
- 纯文本模型只适合 `run_miniwob_click_llm.py`
- 视觉路线默认以截图为主，不把 DOM 文本作为主决策依据，更接近真实 GUI Agent

### 5. 运行真实网页 VLM 演示（最新）

```bash
python scripts/run_real_web_vlm.py
```

当前配置任务：

- 起始页：Wikipedia 主页 `https://en.wikipedia.org/wiki/Main_Page`
- 任务：在页面上的搜索框中搜索 `Artificial intelligence`
- 成功条件：URL 包含 `Artificial_intelligence`

真实网页环境特点：

- 使用 Selenium 驱动 Chrome / Edge
- 自动保存每步截图到 `outputs/real_web_vlm/frames/`
- 自动提取可交互元素（a/button/input/select/textarea 等）
- 支持 CLICK / TYPE / SCROLL / STOP 动作
- 支持输入后自动回车提交搜索
- 点击方式：使用 `document.elementFromPoint` 直接点击坐标并自动聚焦（避免 ActionChains 坐标偏移问题）

已验证结果：

- 真实网页 VLM 演示成功
- 2 步完成
- 总奖励：`1.0`
- `success = True`
- 截图文件：
  - `outputs/real_web_vlm/frames/reset.png`（起始页）
  - `outputs/real_web_vlm/frames/step_1.png`（输入搜索词）
  - `outputs/real_web_vlm/frames/step_2.png`（成功跳转到搜索结果页）

## 当前实现内容

- `MockWebEnv`
  - 用于在不依赖外部 benchmark 的情况下打通 agent loop
- `KeywordGrounder`
  - 基于结构化元素文本的 grounding baseline
- `RuleBasedPolicy`
  - 用于完成最小网页任务的规则策略
- `MiniWoBRulePolicy`
  - 用于完成 `click-test` 一类短程网页 benchmark
- `AgentRunner`
  - 执行循环、日志记录与结果汇总
- `Observation Processors`
  - 将原始 benchmark observation 转成统一结构
- `MiniWoBEnv`
  - MiniWoB++ benchmark 适配层
- `SeleniumWebEnv`
  - 真实网页环境（Selenium 驱动）
  - 支持真实网站截图、元素提取、动作执行
- `LLMGroundedPolicy`
  - 两阶段策略：LLM/VLM 输出动作意图/目标文本，grounding 负责定位并映射到 ref/坐标
  - 支持文本路线（DOM 优先）和视觉路线（截图优先）

## 已验证结果

- `mock agent` 已验证成功
- `MiniWoB click-test-2` 已验证成功
- `真实网页 VLM 演示`（Wikipedia 搜索）已验证成功
- 结果文件位于：
  - `outputs/mock_run/`
  - `outputs/miniwob_click/`
  - `outputs/real_web_vlm/`

## 后续扩展建议

- 接入 `BrowserGym`
- 接入真实截图和 DOM
- 接入多模态模型或 API
- 增加实验配置与评测脚本

## 参考来源

参考仓库来源记录见：

- [docs/references.md](file:///d:/05%20WorkSpace/GUIAgent/docs/references.md)
