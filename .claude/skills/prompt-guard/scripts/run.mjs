#!/usr/bin/env node
/** prompt-guard skill script — runs evaldrift regression tests. */
import { existsSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const cwd = process.cwd();
const hasConfig =
  existsSync(join(cwd, "evaldrift.config.yaml")) ||
  existsSync(join(cwd, ".evaldrift.yaml"));

if (!hasConfig) {
  console.error("未找到 evaldrift.config.yaml，请先运行: npx evaldrift init");
  process.exit(1);
}

const extra = process.argv.slice(2);
const r = spawnSync("npx", ["--yes", "evaldrift@0.1.0", "run", ...extra], {
  cwd,
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(r.status ?? 1);
