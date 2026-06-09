from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenAIChatClient:
    api_key: str
    model: str = "gpt-4.1-mini"
    endpoint: str = "https://api.openai.com/v1/chat/completions"

    @classmethod
    def from_environment(cls) -> "OpenAIChatClient | None":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        return cls(api_key=api_key, model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return f"LLM request failed with HTTP {exc.code}: {detail[:500]}"
        except (urllib.error.URLError, TimeoutError) as exc:
            return f"LLM request failed because the network was unavailable: {exc}"
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            return f"LLM response could not be parsed: {exc}"
