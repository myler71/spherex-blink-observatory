import asyncio
import csv
import io
import time
from typing import Any

import httpx


def _format_http_error(
    exc: Exception,
    method: str,
    url: str,
    timeout: float,
) -> str:
    """Ensure exception has an informative, non-empty error message containing method, url, and timeout/status."""
    raw_msg = str(exc).strip()
    exc_type = type(exc).__name__
    if isinstance(exc, httpx.TimeoutException):
        if not raw_msg:
            return f"{exc_type} after {timeout:.1f}s on {method} {url}"
        return f"{exc_type}: {raw_msg} (timeout={timeout:.1f}s on {method} {url})"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else "unknown"
        if not raw_msg:
            return f"HTTP {code} error on {method} {url}"
        return f"HTTP {code} ({raw_msg}) on {method} {url}"
    if isinstance(exc, httpx.TransportError):
        if not raw_msg:
            return f"{exc_type} network transport error on {method} {url}"
        return f"{exc_type}: {raw_msg} on {method} {url}"
    return raw_msg or f"{exc_type} on {method} {url}"


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    timeout: float = 15.0,
    retries: int = 2,
    total_timeout: float | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Execute HTTP request with bounded retries on transient 5xx/429/network errors; fast-fail on 4xx."""
    last_exc: Exception | None = None
    start_time = time.monotonic()

    for attempt in range(retries + 1):
        current_timeout = timeout
        if total_timeout is not None:
            elapsed = time.monotonic() - start_time
            remaining = total_timeout - elapsed
            if remaining <= 0:
                err_msg = f"Overall timeout of {total_timeout:.1f}s exceeded before attempt {attempt + 1} on {method} {url}"
                if last_exc is not None:
                    raise httpx.ReadTimeout(err_msg) from last_exc
                raise httpx.ReadTimeout(err_msg)
            current_timeout = min(timeout, remaining)

        try:
            # httpx timeouts are per socket phase, not a wall-clock deadline.
            async with asyncio.timeout(remaining if total_timeout is not None else None):
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=current_timeout,
                    follow_redirects=False,
                )
            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = httpx.HTTPStatusError(
                    f"Transient HTTP {resp.status_code} on {method} {url}",
                    request=resp.request,
                    response=resp,
                )
                if attempt < retries:
                    sleep_sec = 0.5 * (2**attempt)
                    if total_timeout is not None:
                        elapsed = time.monotonic() - start_time
                        if (elapsed + sleep_sec) >= total_timeout:
                            raise last_exc
                    await asyncio.sleep(sleep_sec)
                    continue
                raise last_exc
            resp.raise_for_status()
            return resp
        except TimeoutError as exc:
            if total_timeout is None:
                raise
            raise httpx.ReadTimeout(
                f"Overall timeout of {total_timeout:.1f}s exceeded on {method} {url}"
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            formatted_msg = _format_http_error(exc, method, url, current_timeout)
            exc.args = (formatted_msg,)
            last_exc = exc
            if attempt < retries:
                sleep_sec = 0.5 * (2**attempt)
                if total_timeout is not None:
                    elapsed = time.monotonic() - start_time
                    if (elapsed + sleep_sec) >= total_timeout:
                        raise last_exc from exc
                await asyncio.sleep(sleep_sec)
                continue
            raise last_exc from exc
    assert last_exc is not None
    raise last_exc


def parse_csv_rows(text: str) -> list[dict[str, str]]:
    clean = text.strip()
    if not clean:
        return []
    return list(csv.DictReader(io.StringIO(clean)))
