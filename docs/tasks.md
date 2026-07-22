# 完整任务拆解

本文档提供 `GUI Grounding + Web Agent` 小项目的完整实现步骤，不按周期拆分，而是按实际落地顺序展开。你可以把它理解为一份从零到一的执行清单。

---

## 1. 明确项目边界与成功标准

### 1.1 确定最小任务定义

首先明确本项目的最小闭环：

- 输入：
  - 网页任务描述
  - 页面截图
  - 可选 DOM 文本
  - 历史动作
- 输出：
  - 下一步动作
- 动作空间：
  - `CLICK`
  - `TYPE`
  - `SCROLL`
  - `STOP`

### 1.2 确定最小成功标准

项目最少要满足以下条件：

- 能运行一个可重复的网页环境
- 能完成 GUI grounding 的最小推理闭环
- 能完成单步动作预测
- 能形成多步 agent loop
- 至少能在一个 benchmark 或模拟任务集上输出结果

### 1.3 明确阶段性范围

本项目先只做：

- 单智能体
- Web 环境
- 截图为主的 GUI grounding
- 简化或短程网页任务

暂时不做：

- 多智能体协作
- 手机跨 App 长程任务
- 桌面 OS 全流程控制
- 大规模端到端训练

---

## 2. 建立工程骨架

### 2.1 创建基础目录

建议代码仓库统一采用以下目录结构：

```text
GUIAgent/
├─ docs/
├─ configs/
├─ scripts/
├─ src/
│  └─ gui_agent/
│     ├─ env/
│     ├─ grounding/
│     ├─ policy/
│     ├─ executor/
│     ├─ evaluation/
│     └─ utils/
├─ outputs/
└─ README.md
```

### 2.2 补充基础工程文件

需要准备：

- 根目录 `README.md`
- `pyproject.toml`
- `requirements.txt`
- `configs/` 下的默认配置

### 2.3 确定包名和模块职责

推荐包名：

- `gui_agent`

模块职责：

- `env`
  - 环境交互
- `grounding`
  - 文本到界面位置映射
- `policy`
  - 动作决策
- `executor`
  - agent loop 和动作执行
- `evaluation`
  - 指标统计
- `utils`
  - 文件、日志、配置等工具函数

---

## 3. 定义统一的数据结构

这一部分必须尽早完成，否则后面会反复返工。

### 3.1 Observation 结构

建议统一 observation 至少包含：

- `task`
- `screenshot_path`
- `dom_text`
- `elements`
- `history`
- `metadata`

### 3.2 Action 结构

建议统一动作 schema：

```json
{
  "action": "CLICK | TYPE | SCROLL | STOP",
  "value": null,
  "position": [0.5, 0.3]
}
```

说明：

- `CLICK`
  - 需要坐标
- `TYPE`
  - 需要 `value` 和目标输入框位置
- `SCROLL`
  - 需要方向信息
- `STOP`
  - 表示任务结束

### 3.3 GroundingResult 结构

grounding 模块输出建议至少包含：

- `point`
- `bbox`
- `score`
- `query`

### 3.4 StepRecord 结构

每步执行都应该保存记录，便于调试和实验：

- step id
- task id
- observation 摘要
- grounding 结果
- action
- reward
- success / fail

---

## 4. 实现环境层

### 4.1 先实现一个可运行的 Mock 环境

不要一开始直接绑定 BrowserGym 或真实网页 benchmark。推荐先做一个本地 `MockWebEnv`，目的不是发表结果，而是快速打通：

- observation
- action
- transition
- logging

Mock 环境建议具备：

- `reset()`
- `step(action)`
- `close()`
- `render()`

### 4.2 Mock 环境应模拟什么

建议模拟以下信息：

- 页面元素列表
  - 文本
  - 类型
  - bbox
- 页面阶段
  - 初始页
  - 输入后状态
  - 点击后状态
- 任务目标
  - 搜索
  - 点击按钮
  - 打开结果页

### 4.3 再为真实 benchmark 预留适配器接口

当 Mock 环境跑通后，再补：

- `BrowserGymEnv`
- `PlaywrightEnv`

这些适配器先写接口和占位逻辑即可，不必第一版就全部实现。

---

## 5. 实现 Grounding 模块

### 5.1 定义 grounding 抽象接口

需要有统一接口：

```python
predict(screenshot_path, query, elements=None, dom_text=None) -> GroundingResult
```

### 5.2 先做一个规则型 grounding baseline

第一版 grounding 不一定要接大模型，先做可运行 baseline：

- 优先匹配结构化元素文本
- 再用 query 关键词匹配元素名称
- 返回匹配元素中心点和 bbox

### 5.3 后续再替换成 VLM grounding

后续可以替换为：

- API 模型
- 开源 VLM
- 两阶段 grounding 排序器

但第一版一定先保证：

- 接口稳定
- 输出稳定
- 日志可读

### 5.4 需要保存的 grounding 日志

每次 grounding 至少记录：

- query
- 命中元素
- point
- score
- 候选数量

---

## 6. 实现 Policy 模块

### 6.1 定义 policy 抽象接口

统一接口建议为：

```python
act(observation) -> Action
```

### 6.2 先实现一个 rule-based baseline

第一版不必依赖 LLM，先实现规则策略：

- 如果任务要求搜索且输入框存在：
  - 输出 `TYPE`
- 如果已经输入并且按钮存在：
  - 输出 `CLICK`
- 如果结果页已出现：
  - 点击目标结果或 `STOP`

### 6.3 Policy 要依赖哪些输入

建议使用：

- task
- elements
- dom_text
- history
- grounding 工具

### 6.4 Policy 内部要避免什么问题

- 不要把坐标推理和任务规划完全混在一起
- 不要把页面执行细节写进 policy
- 不要让 policy 直接依赖底层环境 API

---

## 7. 实现执行层与 Agent Loop

### 7.1 实现单轮执行器

执行器负责：

- 调用 policy 获取动作
- 将动作送入环境
- 获取下一步 observation
- 写入日志

### 7.2 增加最大步数限制

必须加入：

- `max_steps`

否则 agent 出错后可能陷入无穷循环。

### 7.3 增加停止条件

停止条件包括：

- 环境判定成功
- policy 返回 `STOP`
- 达到最大步数
- 连续失败超过阈值

### 7.4 增加日志和输出目录

每次运行应输出：

- `jsonl` 逐步日志
- 汇总 `summary.json`
- 可选截图与关键步骤记录

---

## 8. 实现评测模块

### 8.1 Grounding 指标

至少实现：

- 命中率
- 平均置信度

### 8.2 Agent 指标

至少实现：

- 成功率
- 平均步数
- 总任务数

### 8.3 增加错误类型统计

建议分类：

- 感知失败
- 定位失败
- 决策失败
- 执行失败

---

## 9. 补充脚本层

至少补以下脚本：

### 9.1 `run_mock_agent.py`

用途：

- 跑完整的 mock 环境 agent demo

### 9.2 `run_grounding_demo.py`

用途：

- 单独演示 grounding 模块

### 9.3 后续预留脚本

后续可再加：

- `run_browsergym_eval.py`
- `collect_results.py`
- `prepare_dataset.py`

---

## 10. 接入真实 benchmark

### 10.1 MiniWoB++ / BrowserGym

推荐优先级最高。

接入时要完成：

- 环境 observation 到统一 Observation 的映射
- benchmark action 到统一 Action 的映射
- 截图与 DOM 信息读取

### 10.2 Mind2Web

更适合作为第二阶段扩展。

接入时要完成：

- 离线样本读取
- 任务和轨迹格式适配
- grounding + action prediction 对接

---

## 11. 做第一轮实验

### 11.1 先跑可重复 demo

先确认：

- Mock 任务可运行
- grounding 输出合理
- rule policy 能完成至少一个任务

### 11.2 再统计最小实验结果

至少生成：

- grounding 命中率
- mock agent 成功率
- 平均步数

### 11.3 保存失败样例

至少保存 3 类失败：

- 定位错
- 动作错
- 已经接近成功但停止条件错

---

## 12. 再做增强版本

建议从下面几个增强项中选一个先做：

### 12.1 DOM 辅助 grounding

在截图外加入 DOM 文本，帮助更稳地匹配目标元素。

### 12.2 候选区域重排序

不是只返回一个点，而是先生成多个候选元素，再排序。

### 12.3 历史动作摘要

避免长历史直接堆入上下文。

### 12.4 错误恢复机制

例如：

- grounding 分数低则回退
- 点击无效则重试或改用候选 2

---

## 13. 输出研究文档与展示材料

最终至少整理以下材料：

- 项目简介
- 系统架构图
- 任务拆解
- 运行说明
- 实验表格
- 失败案例分析
- 技术报告或 PPT 提纲

---

## 14. 最终验收清单

项目结束前确认以下事项均已完成：

- [ ] 工程骨架已建立
- [ ] observation / action / grounding 数据结构统一
- [ ] mock 环境可运行
- [ ] grounding baseline 可运行
- [ ] rule-based policy 可运行
- [ ] agent loop 可运行
- [ ] demo 脚本可运行
- [ ] 至少一种评测统计可运行
- [ ] 日志输出完整
- [ ] 参考来源记录清楚

---

## 15. 参考仓库来源

建议把以下仓库作为后续继续实现时的外部参考来源，并在实际复用代码或设计时保留出处：

- `showlab/ShowUI`
  - 用途：参考 GUI grounding / GUI action 的输入输出形式、轻量 VLA 模型组织方式
- `ServiceNow/BrowserGym`
  - 用途：参考标准化网页环境接口、benchmark 适配方式
- `OSU-NLP-Group/Mind2Web`
  - 用途：参考真实网页任务定义、轨迹样本结构与评测思路

更完整的说明见：

- [references.md](file:///d:/05%20WorkSpace/GUIAgent/docs/references.md)

---

## 16. 一句话执行建议

这个项目最稳的推进方式不是“先做一个很强的模型”，而是：

`先把环境、结构、日志和最小策略闭环打通，再逐步替换 grounding 和 policy 模块。`
