from __future__ import annotations

import json
import os
import re
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self._client = None

    def generate_json(self, prompt: str, schema: dict | None = None) -> str:
        config = {"temperature": 0.2, "response_mime_type": "application/json"}
        if schema:
            config["response_json_schema"] = schema
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as error:
            raise RuntimeError(f"Gemini API request failed: {error}") from error
        if response.text:
            return response.text
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return json.dumps(_jsonable(parsed), ensure_ascii=False)
        raise RuntimeError("Gemini API returned an empty response")

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as error:
                raise RuntimeError("Missing dependency: install google-genai") from error
            self._client = genai.Client(api_key=self.api_key)
        return self._client


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text("utf-8").splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match or line.lstrip().startswith("#"):
            continue
        key, value = match.groups()
        os.environ.setdefault(key, value.strip().strip("\"'"))


def gemini_from_env(model: str | None = None) -> GeminiClient:
    load_dotenv()
    api_key = os.environ.get("GEMINI_API") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API in environment or .env")
    return GeminiClient(api_key=api_key, model=model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
