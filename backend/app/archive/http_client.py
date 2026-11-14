import asyncio
import csv
import io
from typing import Any

import httpx


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    timeout: float = 15.0,
    retries: int = 2,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Execute HTTP request with bounded retries on transient 5xx/429/network errors; fast-fail on 4xx."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
            )
            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = httpx.HTTPStatusError(
                    f"Transient HTTP {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if attempt < retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise last_exc
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def parse_csv_rows(text: str) -> list[dict[str, str]]:
    clean = text.strip()
    if not clean:
        return []
    return list(csv.DictReader(io.StringIO(clean)))
