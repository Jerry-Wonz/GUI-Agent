---
name: api-bridge
description: >
  Use when connecting a REST API to AI agents via MCP. Scaffolds a working,
  testable MCP Server from an OpenAPI spec or curl command using mcp-quickstart.
compatibility: Requires Node.js 18+ and npm.
metadata:
  author: glinks
  version: "0.1.0"
  cli: mcp-quickstart
  homepage: https://github.com/G12789/ai-ship
---

# api-bridge — API → MCP

把现有 REST API 变成 Claude / Cursor 可调用的 MCP Server。

## 何时使用

- 手头有 OpenAPI / Swagger 文档
- 有一条 curl 命令想变成 AI 工具
- 需要团队共享的远程 MCP（Cloudflare Workers）

## 步骤

### 从 OpenAPI

```bash
node scripts/scaffold.mjs my-api-mcp --from-openapi https://example.com/openapi.json
cd my-api-mcp && npm install && npm run dev
```

### 从 curl

```bash
node scripts/scaffold.mjs my-tool --from-curl "curl https://api.example.com/v1/search?q=test -H 'Authorization: Bearer TOKEN'"
```

### 部署到 Cloudflare（可选）

```bash
npm create mcp-quickstart@latest edge-server -- --transport cloudflare -y
```

## 生成后检查

1. `.env.example` 中配置 `API_BASE_URL` 和 auth
2. `npm run inspect` 用 MCP Inspector 验证
3. 在 Cursor / Claude 中添加 MCP 配置

## 失败处理

| 情况 | 处理 |
|---|---|
| OpenAPI 无法访问 | 下载到本地 JSON 再 `--from-openapi ./spec.json` |
| 生成目录已存在 | 换名字或删除旧目录 |

## 相关

- [mcp-quickstart](https://github.com/G12789/mcp-quickstart)
- [ai-ship](https://github.com/G12789/ai-ship)
