#!/usr/bin/env node
/** ship-check skill script — refresh context + evaldrift if configured. */
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";

const cwd = process.cwd();

function runNpx(args) {
  return spawnSync("npx", ["--yes", ...args], {
    cwd,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
}

console.log("→ 刷新项目上下文…");
const out = ".ai/context.md";
mkdirSync(dirname(join(cwd, out)), { recursive: true });

const ctx = runNpx(["--yes", "ctxshot@0.1.0", "--compact", "--diff", "-o", out]);
if (ctx.status !== 0) process.exit(ctx.status ?? 1);

const hasEval =
  existsSync(join(cwd, "evaldrift.config.yaml")) ||
  existsSync(join(cwd, ".evaldrift.yaml"));

if (!hasEval) {
  console.log("→ 跳过 evaldrift（未找到配置文件）");
  console.log("✓ ship-check 完成");
  process.exit(0);
}

console.log("→ 跑 prompt 回归测试…");
const ev = runNpx(["--yes", "evaldrift@0.1.0", "run"]);
process.exit(ev.status ?? 1);
