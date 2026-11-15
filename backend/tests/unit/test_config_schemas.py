import math

import numpy as np
import pytest
from astropy.io import fits
from pydantic import ValidationError

from app.config import Settings
from app.schemas.common import EncodedArray, ErrorResponse
from app.schemas.observe import ObserveQuery
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


def test_settings_defaults_reference_verified_releases_and_flags() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "spherex_dr1" in s.spherex_releases
    assert "spherex_qr3" in s.spherex_releases
    assert 12 not in s.spherex_reject_flag_bits  # FULLSAMPLE must not reject
    assert 21 not in s.spherex_reject_flag_bits  # SOURCE must not reject
    assert {0, 1, 2, 6, 9, 10, 11, 15, 17, 19, 25, 26, 27}.issubset(set(s.spherex_reject_flag_bits))
    assert s.llm_provider == "template"


def test_observe_query_rejects_nan_and_out_of_bounds_coords() -> None:
    with pytest.raises(ValidationError):
        ObserveQuery(ra=math.nan, dec=0.0, fov=0.08)
    with pytest.raises(ValidationError):
        ObserveQuery(ra=361.0, dec=0.0, fov=0.08)
    with pytest.raises(ValidationError):
        ObserveQuery(ra=10.0, dec=-95.0, fov=0.08)
    with pytest.raises(ValidationError):
        ObserveQuery(ra=10.0, dec=0.0, fov=0.9)


def test_encoded_array_float32_and_uint8_roundtrip() -> None:
    arr = np.array([[1.25, -2.5], [0.0, 3.75]], dtype=np.float32)
    enc = EncodedArray.from_numpy(arr)
    assert enc.dtype == "float32"
    assert enc.shape == [2, 2]
    assert enc.encoding == "base64"
    dec = enc.to_numpy()
    assert dec.dtype == np.float32
    np.testing.assert_allclose(dec, arr, rtol=1e-7, atol=1e-7)

    mask = np.array([[0, 1], [5, 255]], dtype=np.uint8)
    enc_m = EncodedArray.from_numpy(mask)
    assert enc_m.dtype == "uint8"
    np.testing.assert_array_equal(enc_m.to_numpy(), mask)


def test_error_response_shape() -> None:
    err = ErrorResponse.create("NO_COVERAGE", "No SPHEREx frames cover position", {"ra": 1.0})
    assert err.model_dump() == {
        "error": {
            "code": "NO_COVERAGE",
            "message": "No SPHEREx frames cover position",
            "details": {"ra": 1.0},
        }
    }


def test_synthetic_fits_generator_matches_verified_hdu_layout(tmp_path) -> None:
    scenario = SyntheticScenario(
        center_ra=180.0,
        center_dec=20.0,
        fov_deg=0.08,
        num_visits=2,
        visit_gap_days=180.0,
        mover_pm_ra_arcsec_yr=8.0,
        mover_pm_dec_arcsec_yr=0.0,
        variable_amplitude=0.35,
        sloped_star_flux=25.0,
        inject_cosmic_rays=2,
    )
    dataset = generate_synthetic_dataset(scenario, tmp_path)
    assert len(dataset.frames) >= 4
    first = dataset.frames[0]
    with fits.open(first.fits_path) as hdul:
        names = [h.name for h in hdul]
        assert names == ["PRIMARY", "IMAGE", "FLAGS", "VARIANCE", "ZODI", "EPSF", "WCS-WAVE"]
        assert hdul["PRIMARY"].header["VERSION"] == "7.0.5"
        assert "DETECTOR" in hdul["IMAGE"].header
        assert "OBSID" in hdul["IMAGE"].header
        assert "MJD-OBS" in hdul["IMAGE"].header
        assert "MSKN0012" in hdul["FLAGS"].header
        assert "MSKN0021" in hdul["FLAGS"].header
    assert dataset.ground_truth_path.exists()
