import asyncio
import re
from io import BytesIO

import httpx
from astropy.io import fits

from app.archive.http_client import parse_csv_rows, request_with_retries
from app.config import Settings
from app.science.ports import ArchiveObservationMeta, CutoutFetchResult
from app.store.cache import CacheStore

_SAFE_URI_RE = re.compile(r"^/?[A-Za-z0-9_./-]+$")


def validate_irsa_relative_uri(raw_uri: str) -> str:
    uri = raw_uri.strip()
    if (
        not uri
        or "://" in uri
        or uri.startswith("//")
        or ".." in uri
        or not _SAFE_URI_RE.match(uri)
    ):
        raise ValueError(f"Unsafe IRSA artifact URI rejected: {raw_uri!r}")
    return uri if uri.startswith("/") else f"/{uri}"


class IrsaArchiveAdapter:
    """IRSA SPHEREx TAP/SIA search and concurrent cutout downloader backed by CacheStore (V-01..V-03)."""

    def __init__(
        self,
        settings: Settings,
        cache: CacheStore,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache
        self._client = client

    async def search_observations(
        self,
        ra_deg: float,
        dec_deg: float,
        releases: list[str] | None = None,
        *,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> list[ArchiveObservationMeta]:
        target_releases = releases or list(self.settings.spherex_releases)
        rel_list_sql = ", ".join(
            f"'{r}'" for r in target_releases if re.match(r"^[A-Za-z0-9_]+$", r)
        )
        where_rel = f" AND o.collection IN ({rel_list_sql})" if rel_list_sql else ""
        sql = (
            "SELECT a.uri AS raw_uri, p.planeid AS plane_id, p.time_bounds_lower, "
            "p.time_bounds_upper, p.energy_bandpassname, p.provenance_version, "
            "o.observationid AS obs_id, o.collection "
            "FROM spherex.artifact a "
            "JOIN spherex.plane p ON a.planeid = p.planeid "
            "JOIN spherex.observation o ON p.obsid = o.obsid "
            f"WHERE 1 = CONTAINS(POINT('ICRS', {ra_deg:.7f}, {dec_deg:.7f}), p.poly)"
            f"{where_rel} "
            "ORDER BY p.time_bounds_lower ASC"
        )

        own_client = self._client is None
        client = self._client or httpx.AsyncClient()
        search_timeout = (
            timeout if timeout is not None else min(self.settings.spherex_http_timeout_sec, 12.0)
        )
        search_retries = (
            retries if retries is not None else min(self.settings.spherex_http_retries, 1)
        )
        total_deadline = search_timeout * (search_retries + 1) + 1.0

        try:
            resp = await request_with_retries(
                client,
                "POST",
                self.settings.irsa_tap_url,
                timeout=search_timeout,
                retries=search_retries,
                total_timeout=total_deadline,
                data={"QUERY": sql, "LANG": "ADQL", "FORMAT": "csv"},
            )
            rows = parse_csv_rows(resp.text)
            out: list[ArchiveObservationMeta] = []
            for r in rows:
                try:
                    rel_uri = validate_irsa_relative_uri(r.get("raw_uri", ""))
                except ValueError:
                    continue
                cutout_url = f"{self.settings.irsa_cutout_base_url.rstrip('/')}{rel_uri}"
                out.append(
                    ArchiveObservationMeta(
                        obs_id=str(r.get("obs_id") or ""),
                        plane_id=str(r.get("plane_id") or ""),
                        collection=str(r.get("collection") or "spherex_dr1"),
                        mjd_start=float(r["time_bounds_lower"])
                        if r.get("time_bounds_lower")
                        else 0.0,
                        mjd_end=float(r["time_bounds_upper"])
                        if r.get("time_bounds_upper")
                        else 0.0,
                        bandpass=str(r.get("energy_bandpassname") or "SPHEREx-D1"),
                        provenance_version=str(r.get("provenance_version") or "7.0"),
                        raw_uri=rel_uri,
                        cutout_url=cutout_url,
                    )
                )
            return out
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            exc_type = type(exc).__name__
            err_msg = str(exc).strip() or f"{exc_type} after {search_timeout:.1f}s"
            raise RuntimeError(f"IRSA TAP archive search failed ({exc_type}): {err_msg}") from exc
        finally:
            if own_client:
                await client.aclose()

    async def fetch_cutouts(
        self,
        observations: list[ArchiveObservationMeta],
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
    ) -> list[CutoutFetchResult]:
        sem = asyncio.Semaphore(self.settings.spherex_cutout_concurrency)
        own_client = self._client is None
        client = self._client or httpx.AsyncClient()

        async def _fetch_one(obs: ArchiveObservationMeta) -> CutoutFetchResult:
            cached = self.cache.get_cutout_path(
                obs.obs_id,
                ra_deg,
                dec_deg,
                fov_deg,
                obs.collection,
                obs.provenance_version,
            )
            if cached is not None:
                return CutoutFetchResult(
                    obs_id=obs.obs_id,
                    archive_url=obs.cutout_url,
                    local_path=cached,
                )

            try:
                rel_uri = validate_irsa_relative_uri(obs.raw_uri)
            except ValueError as exc:
                return CutoutFetchResult(
                    obs_id=obs.obs_id,
                    archive_url=obs.cutout_url,
                    local_path=None,
                    error=str(exc),
                )

            url = (
                f"{self.settings.irsa_cutout_base_url.rstrip('/')}{rel_uri}"
                f"?center={ra_deg:.7f},{dec_deg:.7f}d&size={fov_deg:.4f}"
            )
            async with sem:
                try:
                    resp = await request_with_retries(
                        client,
                        "GET",
                        url,
                        timeout=self.settings.spherex_http_timeout_sec,
                        retries=self.settings.spherex_http_retries,
                        total_timeout=45.0,
                    )
                    raw = resp.content
                    # Validate returned bytes are a readable FITS file
                    with fits.open(BytesIO(raw), memmap=False) as hdul:
                        if "IMAGE" not in hdul and len(hdul) == 0:
                            raise ValueError("Empty FITS response")
                    saved = self.cache.put_cutout_bytes(
                        obs.obs_id,
                        ra_deg,
                        dec_deg,
                        fov_deg,
                        obs.collection,
                        obs.provenance_version,
                        raw,
                    )
                    return CutoutFetchResult(
                        obs_id=obs.obs_id,
                        archive_url=url,
                        local_path=saved,
                    )
                except Exception as exc:
                    exc_type = type(exc).__name__
                    err_msg = str(exc).strip() or f"{exc_type} timeout or download error"
                    formatted_error = (
                        f"{exc_type}: {err_msg}" if not err_msg.startswith(exc_type) else err_msg
                    )
                    return CutoutFetchResult(
                        obs_id=obs.obs_id,
                        archive_url=url,
                        local_path=None,
                        error=formatted_error[:200],
                    )

        try:
            return list(await asyncio.gather(*[_fetch_one(o) for o in observations]))
        finally:
            if own_client:
                await client.aclose()
