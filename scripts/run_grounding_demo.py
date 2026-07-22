from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.grounding.keyword_grounder import KeywordGrounder
from gui_agent.schemas import UIElement


def main() -> None:
    elements = [
        UIElement("search_box", "Search products", "input", [0.10, 0.10, 0.55, 0.18]),
        UIElement("search_button", "Search", "button", [0.60, 0.10, 0.75, 0.18]),
        UIElement("buy_button", "Buy now", "button", [0.70, 0.80, 0.90, 0.90]),
    ]

    grounder = KeywordGrounder()
    result = grounder.predict(
        screenshot_path="mock://demo",
        query="search",
        elements=elements,
        dom_text="Search products Search Buy now",
    )
    print(result.to_dict())


if __name__ == "__main__":
    main()
