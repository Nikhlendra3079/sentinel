from pathlib import Path

TOKEN_BUCKET_LUA = (Path(__file__).parent / "token_bucket.lua").read_text(encoding="utf-8")
