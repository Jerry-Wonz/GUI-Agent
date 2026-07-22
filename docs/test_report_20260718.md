# GUI Agent 测试报告

**日期**: 2026-07-18  
**VLM**: doubao-seed-2.0-lite (火山引擎 Ark)  
**环境**: Selenium Chrome, 非无头模式  
**任务**: 搜索 Google Maps → 打开链接 → 在地图里搜索厦门  
**输出目录**: `outputs/interactive_20260718_205313/`

---

## 执行轨迹

### 阶段 1：百度搜索（Steps 0-7）

| Step | 动作 | 位置 | Grounding 查询 | 匹配元素 | 分数 | 结果 |
|------|------|------|----------------|----------|------|------|
| 0 | CLICK | (0.491, 0.261) | 百度搜索框 | textarea(文心对话) | 0.85 | ✅ |
| 1 | CLICK | (0.491, 0.261) | 搜索框 | textarea | 0.85 | ✅ |
| 2 | TYPE "Google Maps 官网" | (0.029, 0.038) | Google Maps 官网 | **新闻(a标签)** | **0.7** | ❌ invalid element state |
| 3 | TYPE "Google Maps官网" | (0.029, 0.038) | Google Maps官网 | **新闻(a标签)** | **0.7** | ❌ invalid element state |
| 4 | CLICK | (0.491, 0.261) | 搜索框 | textarea | 0.85 | ✅ |
| 5 | CLICK | (0.491, 0.261) | 百度搜索框 | textarea | 0.85 | ✅ |
| 6 | CLICK | (0.491, 0.261) | 百度搜索框 | textarea | 0.85 | ✅ |
| 7 | TYPE "Google Maps官网" | (0.491, 0.261) | 百度搜索框 | textarea | 0.85 | ✅ 输入成功 |

### 阶段 2：百度验证码拦截（Steps 8-10）
Baidu 弹出安全验证（滑块验证码），agent 无法处理， grounding 返回 0.0。

| Step | 动作 | 匹配分数 | 页面 |
|------|------|----------|------|
| 8 | CLICK | 0.0 | 百度安全验证页面 |
| 9 | CLICK | 0.0 | 百度安全验证页面 |
| 10 | CLICK | 0.0 | 百度安全验证页面 |

### 阶段 3：Google Maps（Steps 11-14）
验证通过后回到搜索结果页，agent 点击了 Google Maps 链接，成功进入 Google Maps，但未能执行"搜索厦门"。

| Step | 动作 | 页面 | 说明 |
|------|------|-----|------|
| 11 | CLICK | 百度搜索结果页 | 点击 Google Maps 链接 |
| 12 | CLICK | **google.com/maps** ✅ | 成功到达 Google Maps |
| 13 | CLICK | google.com/maps | 重复点击 |
| 14 | TYPE "Google Maps官网" | google.com/maps | ❌ 未搜索厦门 |

### 最终结果
- **总步数**: 15
- **总奖励**: 0.0
- **成功**: ❌

---

## 发现问题

### P1 - 严重

#### 1. KeywordGrounder 将 TYPE 动作错误匹配到非可输入元素
- **文件**: [src/gui_agent/grounding/keyword_grounder.py](src/gui_agent/grounding/keyword_grounder.py)
- **现象**: 查询词 "Google Maps 官网" 包含子串 "map"，触发了语义提示 `["地图", "map"]` → `{"tag": {"a"}, ...}`，匹配到页面上第一个 a 标签（"新闻"），得分 0.7。TYPE 动作在 a 标签上执行失败。
- **根因**: `_semantic_match()` 没有对 TYPE 动作做输入元素类型限制（只匹配 input/textarea/select）。
- **影响**: 步骤 2-3 完全浪费，共消耗约 15 秒 + 2 次 VLM 调用。
- **修复建议**: 
  - TYPE 动作的 grounding 应优先或仅匹配 `input`、`textarea`、`[contenteditable]` 元素
  - 语义匹配规则应加入元素类型过滤

#### 2. VLM 循环重复动作，无历史记忆
- **文件**: [src/gui_agent/policy/llm_grounded.py](src/gui_agent/policy/llm_grounded.py) → `_build_messages()` 中 `history` 为空
- **现象**: 从 Step 0 到 Step 7，VLM 反复输出 CLICK→TYPE 相同模式，没意识到前序 TYPE 已失败。`observation.history` 始终为 `[]`。
- **根因**: `SeleniumWebEnv._to_observation()` 未填充 `history` 字段，导致 VLM 每一轮都是"盲"决策。
- **影响**: 大量步数被浪费在重复尝试上，agent 无法 from 错误中学习。
- **修复建议**: 在 `Observation` 中加入最近 3-5 步的动作摘要和结果（成功/失败）。

### P2 - 中等

#### 3. 百度安全验证（Captcha）阻断自动化流程
- **现象**: 百度搜索后弹出滑块验证码页面（wappass.baidu.com/static/captcha/tuxing_v2.html），Agent 无法通过验证。
- **根因**: 自动化浏览器触发了百度安全机制。`auto_submit_on_type=True` 导致输入后立即提交，没有模拟人工行为。
- **影响**: 3 个步骤完全无法操作（grounding 得分为 0）。
- **修复建议**: 
  - `auto_submit_on_type` 默认设为 False，先定位"百度一下"按钮再 CLICK
  - 考虑使用更接近人类的浏览器指纹伪装

#### 4. Agent 完成任务到达目标页面后，无法继续推进子任务
- **现象**: 成功到达 Google Maps（Step 12）后，VLM 在 Step 13-14 继续重复旧行为（CLICK 相同位置、再次输入 "Google Maps官网"），没有执行"搜索厦门"。
- **根因**: VLM 的 system prompt 缺少子任务拆解和进度追踪指令。`_build_messages()` 中只有单条任务指令，没有已完成/未完成步骤信息。
- **修复建议**: 
  - 在 system prompt 中加入任务分解引导
  - 将任务进度（已完成的子步骤）注入到每一轮的 prompt 中

### P3 - 建议

#### 5. 缺乏任务完成判定
- 当前的 `_check_success()` 依赖 `success_url_substring` 或 `success_text`，本次未设置任何成功条件，导致即使部分完成也无法获得正奖励。

#### 6. VLM 输出 JSON 不稳定
- `_parse_json()` 是防御性解析，但不处理模型输出非 JSON 格式的情况（如 markdown code block）。如果模型返回 ````json` 包裹的内容，解析会失败。

#### 7. 百度首页布局变化（2026版）
- 百度首页搜索框实际上是 `textarea`（集成文心一言），不是传统的 `input[type=text]` 或 `input[type=search]`。KeywordGrounder 中 `_SEMANTIC_HINTS` 没有包含 `textarea` 作为可接受元素类型，但当前匹配通过通用语义匹配工作。

---

## 总结

Agent 执行了 15 步，**最终到达了 Google Maps 页面**，说明 VLM + Selenium 的基本链路是通的。但存在 **3 个关键阻塞问题** 导致任务未完成：

1. **KeywordGrounder 对 TYPE 动作的错误匹配** → 需要增加元素类型过滤
2. **历史记忆缺失** → VLM 无法感知已尝试过的动作和失败
3. **百度验证码拦截** → 自动化搜索触发安全机制

建议优先修复 P1 问题后，针对"百度→搜索"这个环节设计更稳定的方案，比如直接用 URL 导航替代在百度中搜索。
