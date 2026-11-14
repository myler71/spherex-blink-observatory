from typing import Any

import httpx

from app.archive.http_client import parse_csv_rows, request_with_retries
from app.config import Settings
from app.science.coords import propagate_skycoord


def _opt_float(v: str | None) -> float | None:
    if v is None or v == "" or v.lower() == "nan":
        return None
    try:
        return float(v)
    except ValueError:
        return None


class GaiaAdapter:
    """ESA Gaia DR3 TAP client with documented cap + epoch propagation (FR-16, V-10)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_cone(
        self,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        epochs_mjd: list[float] | None = None,
    ) -> tuple[str, list[dict[str, Any]], bool]:
        radius_deg = max(fov_deg * 0.75, 0.02)
        cap = self.settings.gaia_max_rows
        sql = (
            f"SELECT TOP {cap} source_id, ra, dec, pmra, pmdec, parallax, "
            "phot_g_mean_mag, phot_rp_mean_mag, phot_bp_mean_mag "
            "FROM gaiadr3.gaia_source "
            f"WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_deg:.6f}, {dec_deg:.6f}, {radius_deg:.5f})) "
            "ORDER BY phot_g_mean_mag ASC"
        )
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            resp = await request_with_retries(
                client,
                "POST",
                self.settings.gaia_tap_url,
                timeout=self.settings.catalog_timeout_sec,
                retries=1,
                data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": sql},
            )
            rows = parse_csv_rows(resp.text)
            truncated = len(rows) >= cap
            target_mjd = sum(epochs_mjd) / len(epochs_mjd) if epochs_mjd else 60900.0
            normalized: list[dict[str, Any]] = []
            for r in rows:
                ra = _opt_float(r.get("ra"))
                dec = _opt_float(r.get("dec"))
                if ra is None or dec is None:
                    continue
                pmra = _opt_float(r.get("pmra"))
                pmdec = _opt_float(r.get("pmdec"))
                plx = _opt_float(r.get("parallax"))
                ra_ep, dec_ep = propagate_skycoord(ra, dec, 2016.0, pmra, pmdec, plx, target_mjd)
                normalized.append(
                    {
                        "source_id": r.get("source_id"),
                        "ra": ra,
                        "dec": dec,
                        "ra_epoch": round(ra_ep, 7),
                        "dec_epoch": round(dec_ep, 7),
                        "pmra": pmra,
                        "pmdec": pmdec,
                        "parallax": plx,
                        "phot_g_mean_mag": _opt_float(r.get("phot_g_mean_mag")),
                        "phot_rp_mean_mag": _opt_float(r.get("phot_rp_mean_mag")),
                    }
                )
            return "up", normalized, truncated
        except Exception:
            return "unavailable", [], False
        finally:
            if own:
                await client.aclose()
