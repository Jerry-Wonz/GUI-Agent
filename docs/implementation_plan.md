# 实现方案

## 1. 设计原则

本项目的实现遵循四个原则：

1. `先闭环，后增强`
   - 先跑通从观察到动作执行的最小系统，再做复杂改进
2. `先 grounding，后 planning`
   - 先让系统能看准，再让系统会连续操作
3. `尽量模块化`
   - 感知、决策、执行、评测解耦，方便单独替换
4. `优先支持低算力`
   - 默认支持 API 推理、小模型推理和 LoRA 级微调

## 2. 系统目标

系统需要完成一个标准 agent loop：

1. 读取当前网页观察
2. 根据任务目标和历史动作形成模型输入
3. 输出下一步动作
4. 执行动作并获取新观察
5. 直到成功、失败或超步数结束

## 3. 整体架构

建议系统拆成以下六层：

### 3.1 环境层 `env`

负责网页环境交互。

输入：
- 动作对象

输出：
- 新截图
- 可选 DOM / accessibility 信息
- 执行状态
- 奖励或成功标记

建议能力：
- 打开网页
- 点击
- 输入文本
- 滚动
- 获取截图
- 获取任务完成状态

可选实现：
- Playwright
- BrowserGym
- MiniWoB++ 环境包装器

### 3.2 观察处理层 `observation`

负责将环境状态转成模型可用输入。

输入：
- 截图
- 可选 DOM 信息
- 历史动作

输出：
- 结构化 observation

建议字段：

```json
{
  "task": "在网页中搜索 ThinkPad 并打开价格最低的结果",
  "screenshot_path": "xxx.png",
  "dom_text": "...",
  "history": [
    {"action": "CLICK", "position": [0.42, 0.11]},
    {"action": "TYPE", "value": "ThinkPad", "position": [0.39, 0.10]}
  ]
}
```

### 3.3 Grounding 层 `grounding`

负责将文本目标映射到页面位置。

两种使用方式：

1. `独立 grounding 模块`
   - 先预测目标坐标，再交给动作决策模块
2. `嵌入式 grounding`
   - 模型直接输出动作和坐标

推荐先做第一种，因为更容易调试和评估。

输入：
- 截图
- 文本目标

输出：
- 点击点
  或
- 候选框列表

建议接口：

```python
class Grounder:
    def predict(self, screenshot_path: str, query: str) -> dict:
        return {
            "point": [0.52, 0.24],
            "bbox": [0.48, 0.21, 0.57, 0.27],
            "score": 0.91
        }
```

### 3.4 决策层 `policy`

负责根据任务和观察生成下一步动作。

输入：
- 任务描述
- 当前 observation
- grounding 结果
- 历史动作

输出：
- 标准动作对象

建议动作空间：

```json
{
  "action": "CLICK | TYPE | SCROLL | SELECT | ANSWER | STOP",
  "value": null,
  "position": [0.5, 0.3]
}
```

建议先支持：
- `CLICK`
- `TYPE`
- `SCROLL`
- `STOP`

后续再增加：
- `SELECT`
- `HOVER`
- `ANSWER`

### 3.5 执行与恢复层 `executor`

负责把预测动作转换为环境调用，并处理失败情况。

职责：
- 坐标归一化与像素映射
- 输入框聚焦后再输入
- 页面加载等待
- 异常重试
- 连续失败时触发恢复策略

建议恢复策略：
- 重新截图并重试一次
- 若 grounding 分数低，触发候选区域二次排序
- 若多次点击无效，回退为更保守动作

### 3.6 评测层 `evaluation`

负责统计 grounding 和 agent 两类指标。

输出：
- grounding 正确率
- 任务成功率
- 平均步数
- 错误类型统计

## 4. 推荐目录结构

建议后续代码仓库采用如下结构：

```text
GUIAgent/
├─ docs/
├─ configs/
│  ├─ model/
│  ├─ env/
│  └─ experiment/
├─ data/
│  ├─ raw/
│  ├─ processed/
│  └─ cache/
├─ scripts/
│  ├─ prepare_data.py
│  ├─ run_grounding_eval.py
│  ├─ run_agent_eval.py
│  └─ collect_results.py
├─ src/
│  ├─ env/
│  ├─ observation/
│  ├─ grounding/
│  ├─ policy/
│  ├─ executor/
│  ├─ evaluation/
│  └─ utils/
├─ outputs/
│  ├─ logs/
│  ├─ predictions/
│  └─ reports/
└─ README.md
```

## 5. 最小可行实现 MVP

### 5.1 MVP 目标

实现一个在简化网页环境中执行短任务的 Web Agent。

### 5.2 MVP 组成

- 环境：`MiniWoB++` 或简化 Playwright 网页任务
- 输入：
  - 截图
  - 任务指令
  - 历史动作
- 模型：
  - 基于 API 的多模态模型
  或
  - 小型开源 VLM
- 输出：
  - `CLICK / TYPE / SCROLL / STOP`
- 评测：
  - 任务成功率
  - 平均步数

### 5.3 MVP 不做的事

- 不追求跨站点长程泛化
- 不做大规模训练
- 不引入复杂多智能体框架

## 6. 分阶段实现路线

## 阶段 1：Grounding 单模块跑通

目标：
- 给定截图和文本，输出目标点坐标

建议工作：
- 跑一个 grounding baseline
- 建立统一数据格式
- 评估点击点是否命中目标区域

交付：
- grounding 推理脚本
- grounding 评测脚本

## 阶段 2：单步 Action 预测

目标：
- 给定 observation 输出下一步动作

建议工作：
- 先做 rule + model 混合式系统
- 例如：
  - 先由模型输出“目标元素描述”
  - 再由 grounding 定位
  - 最后组装成动作

交付：
- 标准动作 schema
- 单步预测脚本

## 阶段 3：多步 Agent Loop

目标：
- 在环境里循环执行动作直到结束

建议工作：
- 定义最大步数
- 定义停止条件
- 增加页面等待和失败恢复

交付：
- agent 主循环
- 日志记录器

## 阶段 4：轻量改进

推荐优先级较高的改进项：

1. `历史动作压缩`
   - 只保留最近 k 步和关键状态
2. `候选区域重排序`
   - 先生成多个可点击候选，再排序
3. `截图 + DOM 融合`
   - 用 DOM 文本增强 grounding 或 action 预测
4. `错误恢复`
   - 页面无响应时自动重试

## 7. 接口建议

为了减少后续重构，建议尽早统一接口。

### 7.1 observation 接口

```python
class Observation:
    task: str
    screenshot_path: str
    dom_text: str | None
    history: list[dict]
```

### 7.2 action 接口

```python
class Action:
    action: str
    value: str | None
    position: list[float] | None
```

### 7.3 agent 接口

```python
class WebAgent:
    def act(self, obs: Observation) -> Action:
        ...
```

## 8. 日志与可复现建议

项目初期就建议保存以下信息：

- 每一步截图
- 每一步模型输入摘要
- 每一步动作输出
- grounding 候选结果
- 执行是否成功
- 任务最终状态

推荐输出格式：

- `jsonl` 保存逐步记录
- `csv` 保存汇总指标
- `png` 保存关键截图

## 9. 关键风险与应对

### 风险 1：模型能理解任务，但点不准

应对：
- 单独加强 grounding 模块
- 将动作预测和定位分离

### 风险 2：坐标映射出错

应对：
- 统一使用归一化坐标
- 执行前做截图尺寸到像素的转换校验

### 风险 3：页面动态加载导致操作失效

应对：
- 每次动作后增加显式等待
- 对关键元素加入存在性判断

### 风险 4：长历史导致上下文太长

应对：
- 历史摘要化
- 只保留关键动作和最近状态

## 10. 推荐实现顺序

建议严格按照下面顺序推进：

1. 跑通截图读取与动作执行
2. 跑通 grounding baseline
3. 跑通单步动作生成
4. 组装多步 agent loop
5. 做最小实验
6. 再做轻量改进

这个顺序的核心原因是：项目最容易卡住的不是“模型不够强”，而是环境、坐标和评测闭环没有先打通。
