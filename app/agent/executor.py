"""agent/executor.py - NVIDIA API client. Async, retry, backoff."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import (
    NVIDIA_API_KEY, NVIDIA_BASE_URL,
    MAX_TOKENS, TEMPERATURE, MAX_RETRIES,
)

logger   = logging.getLogger("executor")
_TIMEOUT = httpx.Timeout(90.0, connect=15.0)


async def call_llm(
    model:         str,
    system_prompt: str,
    user_message:  str,
    extra:         Optional[List[Dict[str, str]]] = None,
) -> str:
    """Calls NVIDIA API. Returns content string. Raises RuntimeError on failure."""
    messages: List[Dict] = [{"role": "system", "content": system_prompt}]
    if extra:
        messages.extend(extra)
    messages.append({"role": "user", "content": user_message})

    payload: Dict[str, Any] = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream":      False,
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    logger.info(f"[LLM] -> {model} | tokens={MAX_TOKENS}")
    last_err = "Unknown"

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(
                    f"{NVIDIA_BASE_URL}/chat/completions",
                    json=payload, headers=headers,
                )
                r.raise_for_status()

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            logger.error(f"[LLM] HTTP {code} attempt {attempt}")
            last_err = f"HTTP {code}"
            if code in (400, 401, 403, 422):
                raise RuntimeError(last_err) from e
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(min(1.5 * attempt, 6.0))
                continue
            raise RuntimeError(last_err) from e

        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error(f"[LLM] {type(e).__name__} attempt {attempt}")
            last_err = type(e).__name__
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(min(2.0 * attempt, 8.0))
                continue
            raise RuntimeError(last_err) from e

        try:
            data    = r.json()
            content: str = data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError("Bad response structure") from e

        if not content or not content.strip():
            last_err = "Empty content"
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(1.0)
                continue
            raise RuntimeError(last_err)

        logger.info(f"[LLM] <- {len(content)} chars")
        return content

    raise RuntimeError(f"All attempts failed: {last_err}")
