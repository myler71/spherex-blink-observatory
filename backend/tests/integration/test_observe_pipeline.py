from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.schemas.observe import ObserveQuery
from app.science.pipeline import ObservePipeline
from app.science.ports import ArchiveObservationMeta, CutoutFetchResult
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


class _MockArchive:
    def __init__(self, dataset) -> None:
        self.dataset = dataset
        self.download_calls = 0

    async def search_observations(
        self, ra_deg: float, dec_deg: float, releases: list[str] | None = None
    ) -> list[ArchiveObservationMeta]:
        return [
            ArchiveObservationMeta(
                obs_id=f.obs_id,
                plane_id=f"P_{f.obs_id}",
                collection="spherex_dr1",
                mjd_start=f.mjd,
                mjd_end=f.mjd + 0.005,
                bandpass=f"SPHEREx-D{f.detector}",
                provenance_version="7.0.5",
                raw_uri=f"/syn/{f.obs_id}.fits",
                cutout_url=f"https://irsa.ipac.caltech.edu/syn/{f.obs_id}.fits",
            )
            for f in self.dataset.frames
        ]

    async def fetch_cutouts(
        self,
        observations: list[ArchiveObservationMeta],
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
    ) -> list[CutoutFetchResult]:
        self.download_calls += 1
        by_id = {f.obs_id: f.fits_path for f in self.dataset.frames}
        return [
            CutoutFetchResult(obs_id=o.obs_id, archive_url=o.cutout_url, local_path=by_id[o.obs_id])
            for o in observations
        ]


class _MockCatalogs:
    async def query_all(
        self,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        epochs_mjd: list[float],
        include_neossat: bool = False,
        include_horizons: bool = False,
    ) -> dict[str, Any]:
        return {
            "gaia_status": "up",
            "gaia_rows": [],
            "gaia_truncated": False,
            "allwise_status": "up",
            "allwise_rows": [],
            "simbad_status": "up",
            "simbad_rows": [],
            "vizier_status": "up",
            "vizier_rows": [],
            "ned_status": "up",
            "ned_rows": [],
            "neossat_status": "not_configured",
            "neossat_rows": [],
            "horizons_status": "not_configured",
            "horizons_rows": [],
        }


@pytest.mark.asyncio
async def test_observe_pipeline_end_to_end_synthetic_mover_and_variable(tmp_path: Path) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=2,
            visit_gap_days=365.25,
            detectors=[2],
            n_static_stars=8,
            mover_pm_ra_arcsec_yr=6.0,
            mover_pm_dec_arcsec_yr=0.0,
            mover_flux=70.0,
            variable_amplitude=0.35,
            variable_flux=65.0,
            noise_sigma=0.08,
        ),
        tmp_path,
    )
    pipe = ObservePipeline(settings=settings, archive=_MockArchive(ds), catalogs=_MockCatalogs())
    resp = await pipe.run(ObserveQuery(ra=180.0, dec=20.0, fov=0.08))
    assert resp.served_from == "live"
    assert len(resp.frames) == 4
    assert resp.comparisons.status == "ok"
    assert any(o.is_candidate_moving for o in resp.detected_objects)
    assert any(o.is_variable for o in resp.detected_objects)
    # Successful empty Gaia query -> IR-only no_counterpart
    assert all(o.gaia_counterpart.status == "no_counterpart" for o in resp.detected_objects)
