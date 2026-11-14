from pathlib import Path

SLIDING_WINDOW_LUA = (Path(__file__).parent / "sliding_window.lua").read_text(encoding="utf-8")
