import asyncio
from typing import Any

from app.archive.cadc import CadcNeossatAdapter
from app.archive.gaia import GaiaAdapter
from app.archive.horizons import HorizonsAdapter
from app.archive.ned import NedAdapter
from app.archive.simbad import SimbadAdapter
from app.archive.vizier import VizierAdapter
from app.archive.wise import AllWiseAdapter
from app.config import Settings


class MultiAgencyCatalogBundle:
    """Concurrent multi-agency astronomical catalog adapter implementing CatalogOverlayPort."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gaia = GaiaAdapter(settings)
        self.wise = AllWiseAdapter(settings)
        self.simbad = SimbadAdapter(settings)
        self.vizier = VizierAdapter(settings)
        self.ned = NedAdapter(settings)
        self.cadc = CadcNeossatAdapter(settings)
        self.horizons = HorizonsAdapter(settings)

    async def query_all(
        self,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        epochs_mjd: list[float],
        include_neossat: bool = False,
        include_horizons: bool = False,
    ) -> dict[str, Any]:
        tasks: dict[str, Any] = {
            "gaia": self.gaia.query_cone(ra_deg, dec_deg, fov_deg, epochs_mjd),
            "wise": self.wise.query_cone(ra_deg, dec_deg, fov_deg),
            "simbad": self.simbad.query_cone(ra_deg, dec_deg, fov_deg),
            "vizier": self.vizier.query_cone(ra_deg, dec_deg, fov_deg),
            "ned": self.ned.query_cone(ra_deg, dec_deg, fov_deg),
        }
        if include_neossat:
            tasks["neossat"] = self.cadc.query_cone(ra_deg, dec_deg, fov_deg)
        if include_horizons and epochs_mjd:
            tasks["horizons"] = self.horizons.query_epoch(ra_deg, dec_deg, fov_deg, epochs_mjd[0])

        keys = list(tasks.keys())
        results = await asyncio.gather(*[tasks[k] for k in keys], return_exceptions=True)
        mapped = dict(zip(keys, results, strict=False))

        gaia_res = mapped.get("gaia")
        if isinstance(gaia_res, tuple):
            gaia_status, gaia_rows, gaia_trunc = gaia_res
        else:
            gaia_status, gaia_rows, gaia_trunc = "unavailable", [], False

        def _unpack(
            key: str, default_status: str = "not_configured"
        ) -> tuple[str, list[dict[str, Any]]]:
            val = mapped.get(key)
            if isinstance(val, tuple):
                return val[0], val[1]
            if key in mapped:
                return "unavailable", []
            return default_status, []

        wise_status, wise_rows = _unpack("wise")
        simbad_status, simbad_rows = _unpack("simbad")
        vizier_status, vizier_rows = _unpack("vizier")
        ned_status, ned_rows = _unpack("ned")
        neo_status, neo_rows = _unpack("neossat")
        hor_status, hor_rows = _unpack("horizons")

        return {
            "gaia_status": gaia_status,
            "gaia_rows": gaia_rows,
            "gaia_truncated": gaia_trunc,
            "allwise_status": wise_status,
            "allwise_rows": wise_rows,
            "simbad_status": simbad_status,
            "simbad_rows": simbad_rows,
            "vizier_status": vizier_status,
            "vizier_rows": vizier_rows,
            "ned_status": ned_status,
            "ned_rows": ned_rows,
            "neossat_status": neo_status,
            "neossat_rows": neo_rows,
            "horizons_status": hor_status,
            "horizons_rows": hor_rows,
        }
