# 人机验证 / 验证码拦截解决方案分析

## 1. 问题背景

在 GUI Agent 真实网页执行中，搜索引擎（尤其是百度）和部分目标网站会弹出验证码（captcha）来拦截自动化操作。2026 年 7 月 18 日的测试中，Agent 在百度搜索后触发了 `wappass.baidu.com` 的滑块验证码，导致 3 步完全无法操作（grounding 得分为 0）。

## 2. 验证码触发原因分析

| 触发因素 | 说明 | 优先级 |
|---------|------|--------|
| **自动化浏览器特征** | Selenium 驱动的 Chrome 会暴露 `navigator.webdriver=true` | 高 |
| **操作速度过快** | TYPE 后立即提交，没有人类操作的随机延迟 | 高 |
| **无鼠标轨迹模拟** | 直接 JS click() 没有物理鼠标移动轨迹 | 高 |
| **搜索关键词异常** | 搜索 "Google Maps 官网" 这种跨站搜索请求 | 低 |
| **IP 与 Cookie 特征** | 新浏览器无历史 Cookie，IP 可能被标记 | 中 |

## 3. 解决方案方案

### 方案 A：使用 undetected-chromedriver（推荐）

#### 原理
`undetected-chromedriver` 是一个修补版 Selenium ChromeDriver，会在启动时：
- 自动设置 `navigator.webdriver = false`
- 修补 Chrome 的自动化特征指纹
- 支持正常的 Selenium API

#### 实现

```python
import undetected_chromedriver as uc

driver = uc.Chrome(
    headless=False,
    version_main=150,  # 匹配已安装的 Chrome 版本
)
```

#### 优缺点
- ✅ 实现简单，对现有代码改动小
- ✅ 有效规避大部分基础反爬
- ❌ 对高级滑块验证码（如极验 geetest）无效
- ❌ 需要额外安装依赖

### 方案 B：添加人类行为模拟层（推荐）

#### 原理
在执行动作前加入类人行为特征，降低被侦测的概率。

#### 实现要点

```python
import random
from selenium.webdriver import ActionChains

def human_click(driver, element):
    """模拟人类点击：移动鼠标到元素 → 微调 → 点击"""
    action = ActionChains(driver)
    # 随机偏移，不会每次都点中心
    x_offset = random.randint(-5, 5)
    y_offset = random.randint(-5, 5)
    # 随机延迟
    time.sleep(random.uniform(0.1, 0.3))
    action.move_to_element_with_offset(element, x_offset, y_offset)
    time.sleep(random.uniform(0.05, 0.15))
    action.click()
    action.perform()

def human_type(driver, text):
    """模拟人类逐字输入，带随机间隔"""
    for char in text:
        active = driver.switch_to.active_element
        active.send_keys(char)
        time.sleep(random.uniform(0.05, 0.25))  # 打字速度随机
```

#### 优缺点
- ✅ 大幅降低被侦测概率
- ✅ 和任何 WebDriver 兼容（包括 undetected-chromedriver）
- ✅ 实现简单
- ❌ 增加执行时间
- ❌ 对复杂的滑块验证码仍需额外处理

### 方案 C：验证码检测 + 人工介入（兜底方案）

#### 原理
在执行过程中检测是否出现验证码页面，如果出现则暂停并通知用户手动验证。

#### 实现

```python
_CAPTCHA_KEYWORDS = [
    "captcha", "verify", "验证码", "安全验证",
    "wappass.baidu.com", "geetest", "极验",
]

def is_captcha_page(driver) -> bool:
    url = driver.current_url.lower()
    page_text = driver.find_element("tag name", "body").text.lower()
    return any(kw in url or kw in page_text for kw in _CAPTCHA_KEYWORDS)

def handle_captcha(driver, timeout=120):
    """检测到验证码时暂停，等待人工完成"""
    if not is_captcha_page(driver):
        return True
    print("[!] 检测到验证码页面，请在浏览器中手动完成验证")
    print(f"[!] 等待最多 {timeout} 秒...")
    for i in range(timeout):
        time.sleep(1)
        if not is_captcha_page(driver):
            print("[✓] 验证码已通过")
            return True
    return False
```

#### 优缺点
- ✅ 对任何验证码类型有效
- ✅ 实现最简单
- ❌ 无法全自动运行
- ❌ 在 headless 模式下无效

### 方案 D：直接 URL 导航（最推荐，长期方案）

#### 原理
绕过搜索引擎，直接用 `driver.get(url)` 导航到目标网站，避免搜索引擎的验证码拦截。

#### 实施建议

| 场景 | 方案 |
|------|------|
| 已知目标 URL | 直接 `driver.get("https://www.google.com/maps")` |
| 需要搜索才能找到 URL | 使用 API 搜索（如 Google Search API），获取 URL 后直接导航 |
| 必须通过搜索页面 | 使用 Bing 或 DuckDuckGo（验证码阈值低于百度） |

对于本项目，"在百度搜 Google Maps" 这个步骤完全可以改为：

```python
# 代替在百度中搜索
driver.get("https://www.google.com/maps")
# 然后直接搜索"厦门"
```

### 方案 E：使用 Playwright 替代 Selenium（中长期）

Playwright 相比 Selenium 有：
- 内置更完善的浏览器指纹隐藏
- 原生支持移动端模拟
- 更好的隐身模式

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
        viewport={"width": 1280, "height": 800}
    )
    page = context.new_page()
    page.goto("https://www.baidu.com")
```

## 4. 推荐实施路径

### 短期（立刻可用）

```
1. agent_interactive.py 启动时：
   - 优先使用 undetected_chromedriver（如果已安装）
   - 退回到标准 Selenium ChromeDriver
   
2. 对所有 CLICK / TYPE 动作：
   - 加入随机延迟（0.1-0.5s）
   - TYPE 时逐字输入（已在本次修改中加入）
   
3. 添加验证码检测钩子：
   - 检测到验证码时自动暂停并提示
```

### 中期（本周实施）

```
4. 修改任务设计：
   - 已知目标 URL 时直接导航，不通过搜索引擎
   - 如需搜索，优先使用搜索 API 获取 URL
   
5. 加入浏览器指纹隐藏：
   - 设置自定义 User-Agent
   - 使用 Chrome options 去掉自动化标志
```

### 长期（项目迭代方向）

```
6. 评估是否切换到 Playwright
7. 接入打码平台 API（如 2Captcha）用于全自动场景
8. 建立网站反爬策略库，根据目标网站自动选择最佳方案
```

## 5. 结论

| 方案 | 效果 | 实现成本 | 推荐度 |
|------|------|---------|--------|
| undetected-chromedriver | 中 | 低 | ⭐⭐⭐⭐ |
| 人类行为模拟 | 中 | 低 | ⭐⭐⭐⭐⭐ |
| 验证码检测+人工 | 高 | 最低 | ⭐⭐⭐（后备） |
| 直接 URL 导航 | 最高 | 最低 | ⭐⭐⭐⭐⭐ |
| Playwright 迁移 | 高 | 中 | ⭐⭐⭐（长期） |

**最有效的短期策略：直接 URL 导航（方案 D）+ 人类行为模拟（方案 B）**，避免触发验证码比解决验证码更可靠。
