<!-- ai-ship:vision-auto -->
## Image / Vision (required for text-only models like DeepSeek)

Your base model **CANNOT** see images. When the user attaches or references an image, pastes a screenshot, or you see `[Unsupported Image]` — you **MUST** call MCP `describe_image` or `extract_text` **BEFORE** answering. Do NOT use Read on binary images. Do NOT guess pixels.

| Situation | Tool | mode |
|-----------|------|------|
| General screenshot | `describe_image` | `general` |
| Error dialog / UI | `describe_image` | `ui` |
| Verbatim text | `extract_text` | — |
| Diagram | `describe_image` | `diagram` |
| Before/after | `compare_images` | — |

Example: `describe_image({ "source": "/abs/path.png", "mode": "ui" })`

Cached: `.ai/vision/*.md`
