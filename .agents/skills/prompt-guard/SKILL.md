---
name: prompt-guard
description: >
  Use after editing system prompts, LLM templates, or quality-gate rules.
  Runs evaldrift regression tests against a locked baseline to catch silent
  quality drift. Supports DeepSeek, Kimi, Qwen, Doubao, Ollama via OpenAI-compatible baseUrl.
compatibility: Requires Node.js 18+ and evaldrift.config.yaml in project root (or run evaldrift init first).
metadata:
  author: glinks
  version: "0.1.0"
  cli: evaldrift
  homepage: https://github.com/G12789/ai-ship
---

# prompt-guard — Prompt 防退化

改一句 prompt 可能修好 A 场景、悄悄弄坏 B 场景。本 skill 用 **evaldrift** 做快照式回归测试。

## 何时使用

- 修改 `system` prompt、行业模板、quality-gate 规则后
- 切换模型或 `baseUrl` 后
- 提交 PR 前确认 prompt 未退化

## 步骤

1. 若项目尚无配置，先初始化：

   ```bash
   npx evaldrift init
   npx evaldrift run
   npx evaldrift baseline
   ```

2. 改完 prompt 后执行：

   ```bash
   node scripts/run.mjs
   ```

3. 阅读输出：
   - `PASS` — 全部通过
   - `REGRESSION` — 有退化，列出失败用例
4. 若退化是预期行为，更新基线：`npx evaldrift baseline`

## 国产模型配置示例

```yaml
provider:
  type: openai
  model: deepseek-chat
  baseUrl: https://api.deepseek.com/v1
  apiKeyEnv: DEEPSEEK_API_KEY
```

## 失败处理

| 情况 | 处理 |
|---|---|
| 无配置文件 | 运行 `npx evaldrift init` |
| API Key 缺失 | 检查环境变量；或先用 mock provider 调通断言 |
| 退化 | 修 prompt 或更新 baseline（需人工确认） |

## 相关

- [evaldrift](https://github.com/G12789/evaldrift)
- [ai-ship](https://github.com/G12789/ai-ship)
