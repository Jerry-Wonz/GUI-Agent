---
name: ship-check
description: >
  Use before committing or opening a PR. Refreshes AI context (.ai/context.md)
  and runs evaldrift regression tests if evaldrift.config.yaml exists.
compatibility: Requires Node.js 18+.
metadata:
  author: glinks
  version: "0.1.0"
  cli: ctxshot + evaldrift
  homepage: https://github.com/G12789/ai-ship
---

# ship-check — 发货检查

提交或开 PR 前的轻量检查：**上下文刷新 + prompt 回归**（若有配置）。

## 何时使用

- `git commit` 或 `git push` 之前
- 完成一轮 prompt / 模板修改后
- CI 本地预检

## 步骤

1. 执行：

   ```bash
   node scripts/check.mjs
   ```

   或：

   ```bash
   npx ai-ship check
   ```

2. 检查项：
   - ✅ `.ai/context.md` 已更新（含最新 diff）
   - ✅ evaldrift 全部通过（若存在 `evaldrift.config.yaml`）
3. 再跑项目自己的 `npm test` / `lint`（本 skill 不替代单元测试）

## 输出

- 上下文写入 `.ai/context.md`
- evaldrift 失败时非零退出码，阻止继续提交

## 相关

- [ctxshot](https://github.com/G12789/ctxshot) + [evaldrift](https://github.com/G12789/evaldrift)
- [ai-ship](https://github.com/G12789/ai-ship)
