---
name: vision-auto
description: >
  REQUIRED when main LLM cannot see images (DeepSeek text, local LLMs). Auto-call vision-bridge-mcp
  describe_image/extract_text/compare_images BEFORE answering about screenshots, UI, diagrams, or OCR.
compatibility: Node.js 18+. Requires vision-bridge-mcp in MCP config.
metadata:
  author: glinks
  version: "0.2.0"
  category: mcp
  homepage: https://github.com/G12789/vision-bridge-mcp
---

# vision-auto — 文本模型自动看图（≈ Cursor 截图体验）

## 触发条件（满足任一就必须调 MCP）

- 用户发了截图、设计稿、错误弹窗、终端图
- 消息里出现图片路径、`@xxx.png`、或 `[Unsupported Image]`
- 主模型是 **DeepSeek 文本版** / 其他无视觉模型

**禁止**：用 Read 读二进制图片、凭想象描述像素。

## 双模型架构

```
用户贴图 → Agent 调 describe_image → 旁路视觉模型（Qwen-VL / llava / gpt-4o）
                ↓
         文字描述进上下文 → DeepSeek 继续干活
```

## MCP 配置（推荐通义 Qwen-VL）

```json
{
  "mcpServers": {
    "vision-bridge": {
      "command": "npx",
      "args": ["-y", "vision-bridge-mcp@latest"],
      "env": {
        "VISION_BRIDGE_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "VISION_BRIDGE_API_KEY": "YOUR_KEY",
        "VISION_BRIDGE_MODELS": "qwen-vl-max,qwen2.5-vl-72b-instruct"
      }
    }
  }
}
```

本地零成本：`VISION_BRIDGE_BASE_URL=http://localhost:11434/v1` + `ollama pull llava`

## 工具速查

| 场景 | 工具 | 参数 |
|------|------|------|
| 一般截图 | `describe_image` | `mode: general` |
| UI/报错 | `describe_image` | `mode: ui` |
| 纯文字 OCR | `extract_text` | `source` |
| 架构图/流程图 | `describe_image` | `mode: diagram` |
| TouchDesigner | `describe_image` | `mode: touchdesigner` |
| 前后对比 | `compare_images` | `source_a`, `source_b` |

`source` 支持：本地绝对路径、http(s) URL、`data:image/...`

## 标准流程

1. 识别到图片 → 立即 `describe_image`（不要先回答「我看不到图」）
2. 把返回的 Markdown 当作亲眼所见
3. 同一图再次引用时，可读 `.ai/vision/<hash>.md` 缓存

## CLAUDE.md 硬规则

`ai-ship init` 会注入 `templates/CLAUDE.vision-snippet.md`。
也可调用 MCP 工具 `vision_rules` 获取规则文本。

## 上游致谢

合并自 [claudecode-vision-mcp](https://github.com/look4yo/claudecode-vision-mcp)、[vision-mcp](https://github.com/mohamedhusseinios/vision-mcp)、[image_mcp](https://github.com/karlcc/image_mcp)。
