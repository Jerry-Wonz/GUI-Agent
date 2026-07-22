# 参考仓库与来源说明

本文档记录本项目在设计阶段参考的公开 GitHub 仓库。当前仓库中的实现是重新组织后的最小工程骨架，不直接拷贝外部项目代码；后续如果你继续复用外部仓库中的具体实现，建议在对应文件或提交说明中继续注明来源。

## 1. ShowUI

- 仓库：`https://github.com/showlab/ShowUI`
- 参考用途：
  - GUI grounding / navigation 的输入输出组织方式
  - GUI 动作表示形式
  - 轻量视觉-语言-动作模型的项目结构

本项目借鉴内容：

- 将 GUI 任务拆成 `grounding + action` 两层
- 统一动作 schema
- 用截图作为核心观察输入

本项目未直接复用其训练代码与模型代码，只参考了任务建模思路和工程组织方向。

## 2. BrowserGym

- 仓库：`https://github.com/ServiceNow/BrowserGym`
- 参考用途：
  - 网页 benchmark 统一封装思路
  - web task 环境的标准化接口设计
  - 真实 benchmark 适配路径

本项目借鉴内容：

- 环境层抽象
- observation / action 的统一接口意识
- 后续接入 `MiniWoB++` 等 benchmark 的路线

本项目当前只提供了 `BrowserGymEnv` 预留接口与说明，没有复制其具体实现。

## 3. Mind2Web

- 仓库：`https://github.com/OSU-NLP-Group/Mind2Web`
- 参考用途：
  - 真实网页任务与轨迹样本的定义方式
  - 任务驱动的网页 agent 数据组织思路

本项目借鉴内容：

- 真实网页任务作为第二阶段扩展目标
- 多步轨迹评测的思路

当前工程骨架还没有正式接入其数据处理代码，仅保留扩展方向和适配空间。

## 4. MiniWoB++

- 仓库：`https://github.com/Farama-Foundation/miniwob-plusplus`
- 文档：`https://miniwob.farama.org/`
- 参考用途：
  - 短程网页 benchmark 环境
  - DOM observation 与 action space 的标准形式
  - `click-test` 类任务的最小真实评测入口

本项目借鉴内容：

- `reset / step` 的 Gymnasium 风格封装
- `utterance / fields / screenshot / dom_elements` 的 observation 结构
- `CLICK_ELEMENT / CLICK_COORDS / TYPE_TEXT` 等动作映射思路

本项目当前实现了一个轻量 `MiniWoBEnv` 适配层，但没有复制其 benchmark 代码或环境资源。

## 5. 智谱 BigModel（paas/v4）

- 文档入口：`https://open.bigmodel.cn/`
- 参考用途：
  - 原生 HTTP API 的 chat completions 调用方式
  - 与 OpenAI-compatible 路径区分，避免 `/v1/chat/completions` 这类路径误用

本项目实现：

- 新增 `ZhipuPaaSV4VisionModel` 客户端（不依赖第三方 HTTP 库），用于 `https://open.bigmodel.cn/api/paas/v4` 风格 base_url

## 6. 参考使用原则

后续继续扩展项目时，建议遵循以下原则：

1. 优先参考任务定义、接口设计和评测流程
2. 如果直接移植外部仓库中的代码片段，保留文件级来源说明
3. 若复用配置、脚本或 benchmark adapter，注明原仓库链接
4. 训练代码、模型代码和 benchmark 适配代码尽量分层整理，避免来源混杂
