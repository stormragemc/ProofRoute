"""Only these two endpoints receive authenticated requests."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_MODEL = "moonshotai/Kimi-K3.1-Pro"


class ProviderError(RuntimeError):
    pass


def _post(service, url, key, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=95) as response:
            result = json.load(response)
    except HTTPError as error:
        hints = {
            400: "Check the request and configured model.",
            401: "Check the API key.",
            402: "Check your account credits.",
            403: "Check access for this key and project.",
            404: "Check model availability in Token Factory." if service == "Nebius" else "Check the search endpoint.",
            429: "Check rate limits or remaining credits.",
            432: "Check Tavily's remaining credits.",
        }
        raise ProviderError(f"{service} returned HTTP {error.code}. {hints.get(error.code, 'Try again later.')}") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError(f"{service} could not be reached. Check connectivity and retry.") from None
    except (ValueError, UnicodeError):
        raise ProviderError(f"{service} returned an unreadable response.") from None
    if not isinstance(result, dict):
        raise ProviderError(f"{service} returned an unexpected response.")
    return result


class Providers:
    def __init__(self):
        missing = [key for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY") if not os.getenv(key, "").strip()]
        if missing:
            raise ProviderError("Set the following repository secrets or environment variables: " + ", ".join(missing))
        self.model = os.getenv("NEBIUS_MODEL", "").strip() or DEFAULT_MODEL
        self._nebius_key = os.environ["NEBIUS_API_KEY"].strip()
        self._tavily_key = os.environ["TAVILY_API_KEY"].strip()

    def ask(self, instruction, data):
        request = {
            "model": self.model,
            "max_tokens": 4500,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
        }
        if self.model == DEFAULT_MODEL:
            request["reasoning_effort"] = "low"
        result = _post("Nebius", "https://api.tokenfactory.nebius.com/v1/chat/completions", self._nebius_key, request)
        try:
            raw = result["choices"][0]["message"]["content"].strip()
            if raw.startswith("```") and raw.endswith("```"):
                raw = "\n".join(raw.splitlines()[1:-1])
            answer = json.loads(raw)
            if not isinstance(answer, dict):
                raise ValueError
            return answer
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise ProviderError("Nebius did not return the expected JSON object. Retry or select a different chat model.") from None

    def search(self, query):
        result = _post("Tavily", "https://api.tavily.com/search", self._tavily_key, {
            "query": query,
            "search_depth": "basic",
            "max_results": 4,
            "include_answer": False,
            "include_raw_content": "markdown",
        })
        hits = result.get("results")
        if not isinstance(hits, list):
            raise ProviderError("Tavily did not return a results list.")
        return hits
