---
name: session-start
description: >
  Use when starting a new AI coding session, switching tasks, or when the agent
  needs a fresh project overview. Packs directory tree, npm scripts, README/AGENTS
  summary, and recent git changes into .ai/context.md via ctxshot.
compatibility: Requires Node.js 18+. Run from project root.
metadata:
  author: glinks
  version: "0.1.0"
  cli: ctxshot
  homepage: https://github.com/G12789/ai-ship
---

# session-start — 会话起手

在开始写代码前，先让 Agent 拿到**精简的项目全貌**，避免反复 glob 和重复解释。

## 何时使用

- 新开 Claude Code / Cursor / Codex 会话
- 切换任务或分支后
- 用户说「先熟悉一下项目」「看看结构」

## 步骤

1. 在项目根目录执行：

   ```bash
   node scripts/pack.mjs
   ```

   或（已全局安装 CLI 时）：

   ```bash
   npx ai-ship ctx --compact --diff -o .ai/context.md
   ```

2. 确认生成 `.ai/context.md`
3. 告诉用户：后续对话可 `@.ai/context.md` 或让 Agent 读取该文件
4. 若 `.ai/` 在 `.gitignore` 中，提醒用户这是本地会话缓存

## 输出包含

- 项目目录树（尊重 `.gitignore`）
- `package.json` / `pyproject.toml` 脚本摘要
- `AGENTS.md` / `README.md` 摘录（若存在）
- 最近 git 提交与未提交改动（`--diff`）

## 失败处理

| 情况 | 处理 |
|---|---|
| 无 Node.js | 提示安装 Node 18+ |
| 非 git 仓库 | 仍输出树和 manifest，跳过 diff |
| ctxshot 未安装 | `npx` 会自动拉取 |

## 相关

- 底层工具：[ctxshot](https://github.com/G12789/ctxshot)
- 套件：[ai-ship](https://github.com/G12789/ai-ship)
