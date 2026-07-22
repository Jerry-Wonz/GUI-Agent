from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from gui_agent.env.base import BaseWebEnv
from gui_agent.observation.processors import build_observation, build_ui_elements
from gui_agent.schemas import Action, Observation
from gui_agent.utils.io import ensure_dir


_EXTRACT_ELEMENTS_JS = """
var result = [];
var selectors = 'a, button, input, select, textarea, [role="button"], [onclick], [tabindex], [role="search"], [type="search"]';
var nodes = document.querySelectorAll(selectors);
var idx = 0;
nodes.forEach(function(node) {
    var rect = node.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    var style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return;
    idx += 1;
    var text = (node.innerText || node.value || node.placeholder || node.title ||
                node.getAttribute('aria-label') || node.name || node.id || '').trim();
    var placeholder = (node.placeholder || '').trim();
    var ariaLabel = (node.getAttribute('aria-label') || '').trim();
    var role = (node.getAttribute('role') || '').trim();
    var inputType = (node.type || '').trim();
    var name = (node.name || node.id || '').trim();
    result.push({
        ref: idx,
        tag: node.tagName.toLowerCase(),
        text: text.substring(0, 120),
        placeholder: placeholder.substring(0, 80),
        aria_label: ariaLabel.substring(0, 80),
        role: role,
        input_type: inputType,
        name: name.substring(0, 60),
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height
    });
});
return result;
"""


class SeleniumWebEnv(BaseWebEnv):
    """A real-website environment driven by Selenium WebDriver.

    Opens a live web page, takes screenshots, extracts interactive elements,
    and executes CLICK / TYPE / SCROLL actions. This adapter does not depend
    on any benchmark package — only on Selenium and a local browser.
    """

    def __init__(
        self,
        start_url: str,
        task: str,
        output_dir: str | Path = "outputs/real_web_run",
        window_size: tuple[int, int] = (1024, 768),
        success_text: str | None = None,
        success_url_substring: str | None = None,
        max_steps: int = 10,
        headless: bool = True,
        auto_submit_on_type: bool = False,
        browser: str = "chrome",
    ) -> None:
        self.start_url = start_url
        self.task = task
        self.output_dir = ensure_dir(output_dir)
        self.frames_dir = ensure_dir(self.output_dir / "frames")
        self.window_size = window_size
        self.success_text = success_text
        self.success_url_substring = success_url_substring
        self.max_steps = max_steps
        self.headless = headless
        self.auto_submit_on_type = auto_submit_on_type
        self.browser = browser
        self._step_index = 0
        self._driver = None
        self._screen_size = window_size
        self._ensure_driver()

    def reset(self) -> Observation:
        self._step_index = 0
        self._driver.get(self.start_url)
        time.sleep(1.5)
        return self._to_observation(stage="reset")

    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        self._step_index += 1
        reward = 0.0
        terminated = False
        info: dict[str, Any] = {"step": self._step_index}

        try:
            self._execute_action(action)
        except Exception as exc:
            info["action_error"] = str(exc)

        time.sleep(0.8)

        # 检测验证码页面，等待人工处理
        if self.is_captcha_page(self._driver):
            captcha_passed = self.wait_for_captcha_pass(self._driver, timeout=120)
            if not captcha_passed:
                info["captcha_blocked"] = True
                terminated = True
                info["success"] = False
                observation = self._to_observation(stage=f"step_{self._step_index}_captcha_blocked")
                return observation, reward, terminated, info

        time.sleep(0.5)

        success = self._check_success()
        if success:
            reward = 1.0
            terminated = True
            info["success"] = True
        elif self._step_index >= self.max_steps:
            terminated = True
            info["success"] = False

        observation = self._to_observation(stage=f"step_{self._step_index}")
        return observation, reward, terminated, info

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass

    def compensate_think_time(self, think_time_s: float) -> None:
        """No-op for real websites — there is no built-in episode timer."""
        return None

    def _ensure_driver(self) -> None:
        try:
            from selenium import webdriver
        except ImportError as exc:
            raise ImportError(
                "Selenium is not installed. Run `pip install selenium webdriver-manager` first."
            ) from exc

        self._prepare_browser_runtime()

        if self.browser == "edge":
            from selenium.webdriver.edge.options import Options
            from selenium.webdriver.edge.service import Service
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument(f"--window-size={self.window_size[0]},{self.window_size[1]}")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            try:
                self._driver = webdriver.Edge(options=options)
            except Exception:
                try:
                    from webdriver_manager.microsoft import EdgeChromiumDriverManager
                    service = Service(EdgeChromiumDriverManager().install())
                    self._driver = webdriver.Edge(service=service, options=options)
                except Exception as exc:
                    raise RuntimeError(
                        "Failed to start Edge. Ensure Edge is installed and "
                        "webdriver-manager is available."
                    ) from exc
        else:
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument(f"--window-size={self.window_size[0]},{self.window_size[1]}")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            try:
                self._driver = webdriver.Chrome(options=options)
            except Exception:
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    self._driver = webdriver.Chrome(service=service, options=options)
                except Exception as exc:
                    raise RuntimeError(
                        "Failed to start Chrome. Ensure Chrome is installed and "
                        "webdriver-manager is available."
                    ) from exc

    def _prepare_browser_runtime(self) -> None:
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        for browser_path in self._browser_candidates():
            if browser_path.exists():
                browser_dir = str(browser_path.parent)
                if browser_dir not in path_entries:
                    path_entries.insert(0, browser_dir)
                break
        os.environ["PATH"] = os.pathsep.join(path_entries)

    @staticmethod
    def _browser_candidates() -> list[Path]:
        return [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]

    def _to_observation(self, stage: str) -> Observation:
        screenshot_path = str(self.frames_dir / f"{stage}.png")
        self._driver.save_screenshot(screenshot_path)

        raw_elements = self._driver.execute_script(_EXTRACT_ELEMENTS_JS)
        elements = build_ui_elements(raw_elements, screen_size=self._screen_size)
        current_url = self._driver.current_url

        return build_observation(
            task=self.task,
            screenshot_path=screenshot_path,
            elements=elements,
            metadata={
                "source": "selenium_real_web",
                "stage": stage,
                "current_url": current_url,
                "screen_size": list(self.window_size),
            },
            fields={"start_url": self.start_url},
        )

    def _execute_action(self, action: Action) -> None:
        if action.action == "CLICK":
            self._click(action.position)
        elif action.action == "TYPE":
            if action.position:
                self._click(action.position)
                time.sleep(0.3)
            active = self._driver.switch_to.active_element
            if active:
                from selenium.webdriver.common.keys import Keys
                active.clear()
                # 模拟人类输入速度：逐词暂停，减少被侦测为自动化工具的风险
                text = action.value or ""
                for word in text.split(" "):
                    active.send_keys(word)
                    time.sleep(0.05)
                    if word != text.split(" ")[-1]:
                        active.send_keys(" ")
                        time.sleep(0.05)
                if self.auto_submit_on_type:
                    active.send_keys(Keys.ENTER)
        elif action.action == "SCROLL":
            direction = action.value or "down"
            scroll_y = 400 if direction == "down" else -400
            self._driver.execute_script(f"window.scrollBy(0, {scroll_y});")
        elif action.action == "STOP":
            pass

    def _click(self, position: list[float] | None) -> None:
        if not position:
            return

        width, height = self.window_size
        x = max(0, min(int(position[0] * width), width - 1))
        y = max(0, min(int(position[1] * height), height - 1))
        self._driver.execute_script(
            "var el = document.elementFromPoint(arguments[0], arguments[1]);"
            "if (el) { el.focus(); el.click(); }",
            x,
            y,
        )

    def _get_clicked_element_tag(self) -> str:
        """Get the tag name of the currently focused/active element."""
        try:
            return self._driver.execute_script(
                "return (document.activeElement || {}).tagName || '';"
            ).lower()
        except Exception:
            return ""

    def _check_success(self) -> bool:
        from urllib.parse import unquote

        current_url = self._driver.current_url
        current_url_decoded = unquote(current_url)

        if self.success_url_substring:
            # 同时检查原始 URL 和解码后的 URL，兼容中文和百分号编码
            if self.success_url_substring in current_url or self.success_url_substring in current_url_decoded:
                return True
        if self.success_text:
            body_text = self._driver.find_element("tag name", "body").text
            if self.success_text.lower() in body_text.lower():
                return True
        return False

    @staticmethod
    def is_captcha_page(driver: Any) -> bool:
        """检测当前页面是否为验证码/安全验证页面。"""
        captcha_keywords = [
            "captcha", "verify", "verification", "challenge",
            "验证码", "安全验证", "人机验证",
            "wappass.baidu.com", "geetest", "极验",
            "turnstile", "hcaptcha", "recaptcha",
        ]
        try:
            url = driver.current_url.lower()
            body_text = driver.find_element("tag name", "body").text.lower()
            for kw in captcha_keywords:
                if kw in url or kw in body_text:
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def wait_for_captcha_pass(driver: Any, timeout: int = 120) -> bool:
        """检测到验证码时暂停，等待人工完成验证。返回 True 表示验证通过。"""
        if not SeleniumWebEnv.is_captcha_page(driver):
            return True
        print("\n" + "!" * 60)
        print("  [!] 检测到验证码 / 安全验证页面")
        print("  [!] 请在浏览器中手动完成验证")
        print(f"  [!] 等待最多 {timeout} 秒...")
        print("!" * 60 + "\n")
        for _ in range(timeout):
            import time
            time.sleep(1)
            if not SeleniumWebEnv.is_captcha_page(driver):
                print("[✓] 验证已通过，继续执行。\n")
                return True
        print("[✗] 等待超时，验证未完成。\n")
        return False
