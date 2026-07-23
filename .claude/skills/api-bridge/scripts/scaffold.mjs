#!/usr/bin/env node
/** api-bridge skill script — scaffolds MCP server via mcp-quickstart. */
import { spawnSync } from "node:child_process";

const args = process.argv.slice(2);
if (!args.length) {
  console.error(
    "用法: node scaffold.mjs <name> [--from-openapi <url>] [--from-curl <cmd>]",
  );
  process.exit(1);
}

const r = spawnSync("npm", ["create", "mcp-quickstart@latest", ...args], {
  cwd: process.cwd(),
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(r.status ?? 1);
