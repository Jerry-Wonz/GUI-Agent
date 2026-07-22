from __future__ import annotations

from gui_agent.grounding.base import BaseGrounder
from gui_agent.schemas import GroundingResult, UIElement


# 语义关键词到元素类型/属性的映射
_SEMANTIC_HINTS: list[tuple[list[str], dict]] = [
    # (匹配关键词列表, 评分规则)
    (["搜索框", "search", "search box", "搜索栏", "search bar", "搜索输入"],
     {"tag": {"input", "textarea"}, "type_hint": ["search", "text"], "role": ["search"], "score": 0.85}),
    (["输入框", "input", "输入", "文本框", "text box"],
     {"tag": {"input", "textarea"}, "type_hint": ["text", "search", "email", "url"], "score": 0.75}),
    (["按钮", "button", "提交", "submit", "确定", "ok", "百度一下", "google search", "搜索按钮"],
     {"tag": {"button", "a", "input"}, "type_hint": ["submit", "button"], "score": 0.8}),
    (["登录", "login", "sign in", "log in"],
     {"tag": {"button", "a", "input"}, "type_hint": ["submit"], "score": 0.8}),
    (["地图", "map"],
     {"tag": {"a"}, "attr_key": "text", "score": 0.7}),
]


class KeywordGrounder(BaseGrounder):
    """A lightweight grounding baseline using element text + semantic tag matching."""

    def predict(
        self,
        screenshot_path: str,
        query: str,
        elements: list[UIElement] | None = None,
        dom_text: str | None = None,
    ) -> GroundingResult:
        query_lower = query.lower().strip()
        elements = elements or []

        best: UIElement | None = None
        best_score = 0.0

        for elem in elements:
            text = elem.text.lower()
            attrs = elem.attributes or {}

            # 1. 精确文本匹配（最高优先级）
            if query_lower == text:
                score = 1.0
            elif query_lower in text and text:
                score = 0.9
            elif any(token and token in text for token in query_lower.split() if len(token) > 1):
                score = 0.7
            else:
                # 2. 语义匹配：根据 query 判断目标元素类型
                score = self._semantic_match(query_lower, elem)

            # 3. 属性辅助匹配（placeholder/aria-label/name）
            if score < 0.7:
                score = max(score, self._attr_match(query_lower, attrs))

            if score > best_score:
                best_score = score
                best = elem

        if best is None:
            return GroundingResult(
                query=query,
                point=None,
                bbox=None,
                score=0.0,
                matched_element_id=None,
                matched_ref=None,
                metadata={"candidate_count": len(elements)},
            )

        return GroundingResult(
            query=query,
            point=best.center,
            bbox=best.bbox,
            score=best_score,
            matched_element_id=best.element_id,
            matched_ref=best.ref,
            metadata={"candidate_count": len(elements), "matched_text": best.text[:50], "matched_tag": best.element_type},
        )

    def _semantic_match(self, query_lower: str, elem: UIElement) -> float:
        tag = elem.element_type.lower()
        attrs = elem.attributes or {}
        input_type = str(attrs.get("input_type", "")).lower()
        role = str(attrs.get("role", "")).lower()

        for keywords, rule in _SEMANTIC_HINTS:
            if any(kw in query_lower for kw in keywords):
                # tag 匹配
                if tag in rule.get("tag", set()):
                    # 类型/role 精确匹配加分
                    if input_type in rule.get("type_hint", []) or role in rule.get("role", []):
                        return rule["score"] + 0.05
                    # 对 input/textarea 给基础分
                    return rule["score"]
                # 文本中包含关键词也给分
                text = elem.text.lower()
                attr_text = " ".join(str(v).lower() for v in attrs.values() if isinstance(v, str))
                if any(kw in text or kw in attr_text for kw in keywords):
                    return rule["score"] - 0.1
        return 0.0

    def _attr_match(self, query_lower: str, attrs: dict) -> float:
        """在 placeholder / aria_label / name / title 中查找匹配。"""
        for key in ("placeholder", "aria_label", "name", "title"):
            val = str(attrs.get(key, "")).lower()
            if not val:
                continue
            if query_lower in val or val in query_lower:
                return 0.8
            # 关键词部分匹配
            for token in query_lower.split():
                if len(token) > 1 and token in val:
                    return 0.7
        return 0.0
