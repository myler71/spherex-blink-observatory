import pytest
from astropy.time import Time

from app.config import Settings
from app.science.coords import parse_ra_dec, propagate_skycoord
from app.science.ports import ArchiveObservationMeta
from app.science.select import select_observations
from app.science.targets import get_target_preset, list_target_presets


def test_mandatory_targets_include_five_plus_negative_control() -> None:
    presets = list_target_presets()
    ids = {p.id for p in presets}
    assert {
        "barnards_star",
        "wise_0855",
        "epsilon_indi_b",
        "rw_aurigae",
        "r_draconis",
        "negative_control",
    }.issubset(ids)
    nc = get_target_preset("negative_control")
    assert nc is not None and nc.is_negative_control


def test_parse_ra_dec_decimal_and_sexagesimal() -> None:
    ra1, dec1 = parse_ra_dec("269.452075", "4.693389")
    assert ra1 == pytest.approx(269.452075, abs=1e-6)
    assert dec1 == pytest.approx(4.693389, abs=1e-6)

    # Barnard's Star HMS/DMS
    ra2, dec2 = parse_ra_dec("17h57m48.5s", "+04d41m36s")
    assert ra2 == pytest.approx(269.452083, abs=1e-3)
    assert dec2 == pytest.approx(4.693333, abs=1e-3)


def test_barnards_star_epoch_propagation_to_2026() -> None:
    b = get_target_preset("barnards_star")
    assert b is not None
    # Propagate from J2016.0 to 2026-06-01 (~10.4 yr * 10.39 arcsec/yr = ~108 arcsec)
    target_mjd = float(Time("2026-06-01T00:00:00", scale="utc").mjd)
    ra_p, dec_p = propagate_skycoord(
        ra_deg=b.ra_deg,
        dec_deg=b.dec_deg,
        ref_epoch_jyear=b.ref_epoch_jyear,
        pm_ra_mas_yr=b.pm_ra_mas_yr,
        pm_dec_mas_yr=b.pm_dec_mas_yr,
        parallax_mas=b.parallax_mas,
        target_mjd=target_mjd,
    )
    # Dec moves ~10.362 arcsec/yr * 10.41 yr = +107.9 arcsec = +0.02997 deg
    assert (dec_p - b.dec_deg) * 3600.0 == pytest.approx(10.362 * 10.415, abs=1.0)
    assert ra_p != b.ra_deg


def test_select_observations_spans_180d_baseline_and_deduplicates() -> None:
    settings = Settings()
    # Build two visits 180 days apart plus duplicate observationid across DR1/QR3
    obs = [
        ArchiveObservationMeta(
            obs_id="OBS_V0_A",
            plane_id="P1",
            collection="spherex_qr3",
            mjd_start=60800.0,
            mjd_end=60800.01,
            bandpass="SPHEREx-D2",
            provenance_version="7.0.5",
            raw_uri="/a.fits",
            cutout_url="https://irsa.ipac.caltech.edu/a.fits",
        ),
        ArchiveObservationMeta(
            obs_id="OBS_V0_A",  # duplicate obs_id in DR1 (should prefer DR1)
            plane_id="P1b",
            collection="spherex_dr1",
            mjd_start=60800.0,
            mjd_end=60800.01,
            bandpass="SPHEREx-D2",
            provenance_version="7.0.6",
            raw_uri="/a_dr1.fits",
            cutout_url="https://irsa.ipac.caltech.edu/a_dr1.fits",
        ),
        ArchiveObservationMeta(
            obs_id="OBS_V0_B",
            plane_id="P2",
            collection="spherex_dr1",
            mjd_start=60800.2,
            mjd_end=60800.21,
            bandpass="SPHEREx-D3",
            provenance_version="7.0.6",
            raw_uri="/b.fits",
            cutout_url="https://irsa.ipac.caltech.edu/b.fits",
        ),
        ArchiveObservationMeta(
            obs_id="OBS_V1_A",
            plane_id="P3",
            collection="spherex_dr1",
            mjd_start=60980.0,
            mjd_end=60980.01,
            bandpass="SPHEREx-D2",
            provenance_version="7.0.6",
            raw_uri="/c.fits",
            cutout_url="https://irsa.ipac.caltech.edu/c.fits",
        ),
    ]
    res = select_observations(obs, max_frames=12, settings=settings)
    obs_ids = [o.obs_id for o in res.selected]
    assert len(obs_ids) == 3  # deduplicated OBS_V0_A
    # Kept DR1 for OBS_V0_A
    kept_a = [o for o in res.selected if o.obs_id == "OBS_V0_A"][0]
    assert kept_a.collection == "spherex_dr1"
    assert res.baseline_days == pytest.approx(180.0, abs=0.5)
    assert res.visits_count == 2
    assert not res.single_visit_warning


def test_select_observations_single_visit_emits_warning() -> None:
    settings = Settings()
    obs = [
        ArchiveObservationMeta(
            obs_id="OBS_1",
            plane_id="P1",
            collection="spherex_dr1",
            mjd_start=60800.0,
            mjd_end=60800.01,
            bandpass="SPHEREx-D2",
            provenance_version="7.0.6",
            raw_uri="/1.fits",
            cutout_url="https://irsa.ipac.caltech.edu/1.fits",
        )
    ]
    res = select_observations(obs, max_frames=12, settings=settings)
    assert res.visits_count == 1
    assert res.baseline_days == 0.0
    assert res.single_visit_warning is not None
