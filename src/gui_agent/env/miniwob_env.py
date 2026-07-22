from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from gui_agent.env.base import BaseWebEnv
from gui_agent.observation.processors import build_observation, build_ui_elements, save_rgb_image
from gui_agent.schemas import Action, Observation
from gui_agent.utils.io import ensure_dir


class MiniWoBEnv(BaseWebEnv):
    """
    Adapter for MiniWoB++ environments.

    This adapter is intentionally lightweight and currently targets short-horizon
    tasks such as click-test variants. It keeps the project compatible with the
    existing agent abstractions without copying benchmark-specific code.
    """

    def __init__(
        self,
        env_name: str = "miniwob/click-test-2-v1",
        output_dir: str | Path = "outputs/miniwob_run",
        render_mode: str | None = None,
        seed: int | None = 42,
        episode_timeout_ms: int | None = None,
    ) -> None:
        self.env_name = env_name
        self.output_dir = ensure_dir(output_dir)
        self.frames_dir = ensure_dir(self.output_dir / "frames")
        self.render_mode = render_mode
        self.seed = seed
        self.episode_timeout_ms = episode_timeout_ms
        self._step_index = 0
        self._env = None
        self._action_types = None
        self._screen_size = (160, 210)
        self._ensure_backend()

    def reset(self) -> Observation:
        self._step_index = 0
        raw_obs, info = self._env.reset(seed=self.seed)
        self._apply_episode_timeout_override()
        return self._to_observation(raw_obs, info, stage="reset")

    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        translated_action = self._translate_action(action)
        raw_obs, reward, terminated, truncated, info = self._env.step(translated_action)
        self._step_index += 1
        info = dict(info or {})
        info["truncated"] = truncated
        observation = self._to_observation(raw_obs, info, stage=f"step_{self._step_index}")
        return observation, float(reward), bool(terminated or truncated), info

    def close(self) -> None:
        if self._env is not None:
            self._env.close()

    def compensate_think_time(self, seconds: float) -> None:
        if self._env is None or seconds <= 0:
            return
        instance = getattr(self._env.unwrapped, "instance", None)
        start_time = getattr(instance, "start_time", None)
        if instance is None or not isinstance(start_time, (int, float)):
            return
        # MiniWoB counts wall-clock time from episode start. For remote VLM calls,
        # exclude agent inference latency so the benchmark reflects action quality.
        instance.start_time += float(seconds)

    def _apply_episode_timeout_override(self) -> None:
        if self._env is None or not self.episode_timeout_ms:
            return
        instance = getattr(self._env.unwrapped, "instance", None)
        driver = getattr(instance, "driver", None)
        if driver is None:
            return
        timeout_ms = int(self.episode_timeout_ms)
        driver.execute_script(
            """
            if (window.core) {
              core.EPISODE_MAX_TIME = arguments[0];
              if (core.EP_TIMER !== null) {
                clearTimeout(core.EP_TIMER);
              }
              core.ept0 = new Date().getTime();
              core.countdownTimer(core.EPISODE_MAX_TIME);
              core.EP_TIMER = setTimeout(function() {
                core.endEpisode(-1, false, 'timed out');
              }, core.EPISODE_MAX_TIME);
            }
            """,
            timeout_ms,
        )

    def _ensure_backend(self) -> None:
        try:
            import gymnasium
            import miniwob
            from miniwob.action import ActionTypes
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise ImportError(
                "MiniWoB backend is not installed. Install `gymnasium` and `miniwob` first."
            ) from exc

        self._prepare_browser_runtime()
        gymnasium.register_envs(miniwob)
        try:
            self._env = gymnasium.make(self.env_name, render_mode=self.render_mode)
        except Exception as exc:  # pragma: no cover - depends on local browser runtime
            raise RuntimeError(
                "MiniWoB environment initialization failed. "
                "Please ensure Chrome and chromedriver are available. "
                "You can also install webdriver-manager and rerun the script."
            ) from exc
        self._action_types = ActionTypes

    def _prepare_browser_runtime(self) -> None:
        """
        Try to expose browser and driver binaries to Selenium/MiniWoB.
        """
        path_entries = os.environ.get("PATH", "").split(os.pathsep)

        for browser_path in self._browser_candidates():
            if browser_path.exists():
                browser_dir = str(browser_path.parent)
                if browser_dir not in path_entries:
                    path_entries.insert(0, browser_dir)
                break

        try:
            from webdriver_manager.chrome import ChromeDriverManager

            driver_path = Path(ChromeDriverManager().install())
            driver_dir = str(driver_path.parent)
            if driver_dir not in path_entries:
                path_entries.insert(0, driver_dir)
        except Exception:
            pass

        os.environ["PATH"] = os.pathsep.join(path_entries)

    @staticmethod
    def _browser_candidates() -> list[Path]:
        return [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]

    def _to_observation(
        self,
        raw_obs: dict[str, Any],
        info: dict[str, Any],
        stage: str,
    ) -> Observation:
        fields = dict(raw_obs.get("fields", ()))
        screenshot = raw_obs.get("screenshot")
        screenshot_path = ""
        if screenshot is not None:
            try:
                self._screen_size = (int(screenshot.shape[1]), int(screenshot.shape[0]))
            except Exception:
                self._screen_size = (160, 210)
            screenshot_path = save_rgb_image(
                screenshot,
                output_dir=self.frames_dir,
                filename=f"{stage}.ppm",
            )

        elements = build_ui_elements(raw_obs.get("dom_elements", ()), screen_size=self._screen_size)
        return build_observation(
            task=str(raw_obs.get("utterance", "")),
            screenshot_path=screenshot_path or f"miniwob://{stage}",
            elements=elements,
            metadata={
                "source": "miniwob",
                "env_name": self.env_name,
                "stage": stage,
                "task_type": "click_element",
                "screen_size": list(self._screen_size),
                "info": info,
            },
            fields=fields,
        )

    def _translate_action(self, action: Action) -> dict[str, Any]:
        assert self._env is not None
        assert self._action_types is not None

        unwrapped = self._env.unwrapped
        ref = action.metadata.get("ref")

        if action.action == "CLICK":
            if ref is not None:
                return unwrapped.create_action(self._action_types.CLICK_ELEMENT, ref=ref)

            coords = self._normalized_to_pixels(action.position)
            return unwrapped.create_action(self._action_types.CLICK_COORDS, coords=coords)

        if action.action == "TYPE":
            if ref is not None:
                return unwrapped.create_action(
                    self._action_types.FOCUS_ELEMENT_AND_TYPE_TEXT,
                    ref=ref,
                    text=action.value or "",
                )
            return unwrapped.create_action(self._action_types.TYPE_TEXT, text=action.value or "")

        if action.action == "SCROLL":
            coords = self._normalized_to_pixels(action.position or [0.5, 0.5])
            if action.value == "up":
                return unwrapped.create_action(self._action_types.SCROLL_UP_COORDS, coords=coords)
            return unwrapped.create_action(self._action_types.SCROLL_DOWN_COORDS, coords=coords)

        return unwrapped.create_action(self._action_types.NONE)

    def _normalized_to_pixels(self, position: list[float] | None) -> tuple[int, int]:
        if not position:
            return (0, 0)
        x = max(0.0, min(1.0, float(position[0])))
        y = max(0.0, min(1.0, float(position[1])))
        width, height = self._screen_size
        return (int(x * width), int(y * height))
