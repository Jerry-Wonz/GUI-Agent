#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const cwd = process.cwd();
const outIdx = process.argv.indexOf("--out");
const out =
  outIdx >= 0 && process.argv[outIdx + 1]
    ? process.argv[outIdx + 1]
    : ".ai/context.md";

mkdirSync(dirname(resolve(cwd, out)), { recursive: true });

const args = ["--yes", "ctxshot@0.1.0", "--compact", "--diff", "-o", out];

const r = spawnSync("npx", args, {
  cwd,
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(r.status ?? 1);
