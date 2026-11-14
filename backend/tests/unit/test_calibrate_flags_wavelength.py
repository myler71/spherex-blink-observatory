from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
import pytest

from app.config import Settings
from app.science.calibrate import calibrate_cutout
from app.science.flags import build_flag_mask_and_summary
from app.science.wavelength import compute_wavelength_at_pixels
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


def test_flags_mask_preserves_fullsample_and_source_bits(tmp_path: Path) -> None:
    settings = Settings()
    flags = np.zeros((10, 10), dtype=np.int32)
    flags[:, :] = 1 << 12  # FULLSAMPLE
    flags[3, 3] |= 1 << 21  # SOURCE
    flags[5, 5] |= 1 << 0   # TRANSIENT (reject)
    flags[7, 8] |= 1 << 10  # HOT (reject)

    bad_mask, u8_mask, summary = build_flag_mask_and_summary(
        flags, reject_bits=settings.spherex_reject_flag_bits
    )
    expected_bad = np.zeros((10, 10), dtype=bool)
    expected_bad[5, 5] = True
    expected_bad[7, 8] = True
    np.testing.assert_array_equal(bad_mask, expected_bad)
    assert not bad_mask[3, 3]
    assert summary.rejected_pixels == 2
    assert (u8_mask[3, 3] & (1 << 2)) != 0  # SOURCE bit packed in uint8


def test_calibrate_and_wavelength_on_synthetic_and_missing_zodi(tmp_path: Path) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(detectors=[2], exposures_per_visit=1, num_visits=1),
        tmp_path,
    )
    fpath = ds.frames[0].fits_path
    cal = calibrate_cutout(
        fpath,
        archive_url="https://example.test/cutout.fits",
        release="spherex_dr1",
        settings=settings,
    )
    assert cal.image.dtype == np.float32
    assert cal.image.flags["C_CONTIGUOUS"]
    assert cal.provenance.zodi_level_mjy_sr == pytest.approx(1.5, abs=0.1)
    assert cal.provenance.central_wavelength_um is not None
    assert 1.10 <= cal.provenance.central_wavelength_um <= 1.62

    # Missing ZODI produces warning, not exception
    no_zodi_path = tmp_path / "no_zodi.fits"
    with fits.open(fpath) as hdul:
        new_hdul = fits.HDUList([h for h in hdul if h.name != "ZODI"])
        new_hdul.writeto(no_zodi_path, overwrite=True)

    cal2 = calibrate_cutout(
        no_zodi_path,
        archive_url="https://example.test/no_zodi.fits",
        release="spherex_dr1",
        settings=settings,
    )
    assert any("ZODI" in w for w in cal2.warnings)


def test_real_fixtures_wavelength_and_epsf_dynamic_rows(fixtures_dir: Path) -> None:
    settings = Settings()
    for name, ra, dec, lo, hi in [
        ("barnards_star_sample.fits", 269.452075, 4.693389, 0.75, 5.05),
        ("wise_0855_sample.fits", 133.795129, -7.245147, 0.75, 5.05),
    ]:
        fpath = fixtures_dir / name
        if not fpath.exists():
            pytest.skip(f"Fixture {name} missing")
        cal = calibrate_cutout(
            fpath,
            archive_url=f"file://{name}",
            release="spherex_dr1",
            settings=settings,
        )
        assert cal.provenance.central_wavelength_um is not None
        assert lo <= cal.provenance.central_wavelength_um <= hi

        # Compare WCS-WAVE directly against IRSA tutorial reference method
        with fits.open(fpath) as hdul:
            swcs = WCS(hdul["IMAGE"].header, fobj=hdul, key="W")
            swcs.sip = None
            ny, nx = hdul["IMAGE"].data.shape
            wl_ref, bw_ref = swcs.pixel_to_world(nx / 2.0, ny / 2.0)
            wl_calc, bw_calc = compute_wavelength_at_pixels(
                hdul, np.array([nx / 2.0]), np.array([ny / 2.0])
            )
            assert abs(wl_calc[0] - float(wl_ref.to_value("um"))) <= 0.01 * float(
                bw_ref.to_value("um")
            )
