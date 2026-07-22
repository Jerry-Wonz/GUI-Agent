# GUI Grounding + Web Agent 小项目文档

本目录整理了一个适合研究生落地实践的 `GUI Grounding + Web Agent` 小项目方案。文档目标不是只给出选题描述，而是直接支持后续实现、实验、汇报和论文雏形整理。

## 文档说明

- `project_overview.md`
  - 项目背景、目标、范围、技术路线、阶段里程碑
- `implementation_plan.md`
  - 系统架构、模块划分、输入输出接口、目录结构建议、实现迭代方案
- `experiment_plan.md`
  - 数据集、评测指标、baseline、消融实验、硬件预算与预期结果
- `tasks.md`
  - 完整任务拆解，按实现顺序展开
- `references.md`
  - 参考 GitHub 仓库来源和使用说明

## 建议阅读顺序

1. 先看 `project_overview.md`，明确项目边界
2. 再看 `implementation_plan.md`，确定具体怎么做
3. 然后看 `experiment_plan.md`，避免实现后没有评测闭环
4. 然后按 `tasks.md` 直接执行实现
5. 需要补 benchmark 或模型时，再查 `references.md`

## 项目定位

本项目聚焦一个低算力、可复现、可扩展的研究实践路径：

- 从 `GUI Grounding` 入手，先解决“看图定位可操作元素”
- 再扩展到 `Web Agent`，解决“根据任务执行点击/输入/滚动等网页动作”
- 优先完成单机可跑的最小闭环
- 在此基础上做轻量改进，而不是一开始追求大规模训练

## 推荐最小目标

如果时间和算力都有限，建议优先完成以下闭环：

1. 在截图上完成元素定位
2. 在简化网页环境中完成单步或短程操作
3. 在 `MiniWoB++` 或相近 Web benchmark 上统计成功率
4. 对比一个 baseline，并给出错误案例分析

## 适合的产出形式

这套方案适合发展为以下任一成果：

- 课程项目
- 实验室组会汇报
- 阶段性技术报告
- 小论文雏形
- 后续更大 GUI Agent 项目的基础仓库
