from io import BytesIO
from pathlib import Path

import httpx
import pytest
from astropy.io import fits

from app.archive.ads import AdsAdapter
from app.archive.cadc import CadcNeossatAdapter
from app.archive.gaia import GaiaAdapter
from app.archive.horizons import HorizonsAdapter
from app.archive.irsa import IrsaArchiveAdapter, validate_irsa_relative_uri
from app.archive.ned import NedAdapter
from app.archive.simbad import SimbadAdapter
from app.archive.vizier import VizierAdapter
from app.archive.wise import AllWiseAdapter
from app.config import Settings
from app.science.ports import ArchiveObservationMeta
from app.store.cache import CacheStore


def test_validate_irsa_relative_uri_blocks_ssrf_and_traversal() -> None:
    assert (
        validate_irsa_relative_uri("ibe/data/spherex/dr1/level2/test.fits")
        == "/ibe/data/spherex/dr1/level2/test.fits"
    )
    with pytest.raises(ValueError):
        validate_irsa_relative_uri("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(ValueError):
        validate_irsa_relative_uri("/ibe/../etc/passwd")


@pytest.mark.asyncio
async def test_irsa_cutout_cache_hit_and_partial_failure(tmp_path: Path) -> None:
    settings = Settings(cache_dir=str(tmp_path / "cache"))
    cache = CacheStore(settings)

    # Build valid FITS bytes in memory
    buf = BytesIO()
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(name="IMAGE")]).writeto(buf)
    fits_bytes = buf.getvalue()

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "fail.fits" in str(request.url):
            return httpx.Response(503, text="Upstream busy")
        return httpx.Response(200, content=fits_bytes)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = IrsaArchiveAdapter(settings=settings, cache=cache, client=client)

    obs = [
        ArchiveObservationMeta(
            obs_id="OBS_OK",
            plane_id="P1",
            collection="spherex_dr1",
            mjd_start=60800.0,
            mjd_end=60800.01,
            bandpass="SPHEREx-D2",
            provenance_version="7.0.5",
            raw_uri="ibe/data/spherex/ok.fits",
            cutout_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/ok.fits?center=10,10d&size=0.08",
        ),
        ArchiveObservationMeta(
            obs_id="OBS_FAIL",
            plane_id="P2",
            collection="spherex_dr1",
            mjd_start=60801.0,
            mjd_end=60801.01,
            bandpass="SPHEREx-D2",
            provenance_version="7.0.5",
            raw_uri="ibe/data/spherex/fail.fits",
            cutout_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/fail.fits?center=10,10d&size=0.08",
        ),
    ]

    res1 = await adapter.fetch_cutouts(obs, 10.0, 10.0, 0.08)
    assert res1[0].local_path is not None and res1[0].local_path.exists()
    assert res1[1].local_path is None and res1[1].error is not None

    # Second call for OBS_OK must perform ZERO HTTP downloads (cache hit)
    prev_calls = calls["n"]
    res2 = await adapter.fetch_cutouts([obs[0]], 10.0, 10.0, 0.08)
    assert res2[0].local_path is not None
    assert calls["n"] == prev_calls
    await client.aclose()


@pytest.mark.asyncio
async def test_simbad_mirror_failover_on_404_and_gaia_truncation() -> None:
    settings = Settings(
        simbad_tap_urls=[
            "https://primary.simbad.test/sim-tap/sync",
            "https://mirror.simbad.test/sim-tap/sync",
        ],
        gaia_max_rows=2,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "primary.simbad.test" in url:
            return httpx.Response(404, text="Not found")
        if "mirror.simbad.test" in url:
            return httpx.Response(
                200,
                text='main_id,otype,ra,dec,pmra,pmdec,plx_value\n"Barnard\'s Star","PM*",269.45,4.73,-801.5,10362.4,546.9\n',
            )
        if "gea.esac.esa.int" in url:
            return httpx.Response(
                200,
                text=(
                    "source_id,ra,dec,pmra,pmdec,parallax,phot_g_mean_mag\n"
                    "1,269.45,4.73,-801.5,10362.4,546.9,8.19\n"
                    "2,269.46,4.74,0.1,0.1,1.0,12.0\n"
                ),
            )
        return httpx.Response(200, text="col1\n")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    simbad = SimbadAdapter(settings=settings, client=client)
    s_status, s_rows = await simbad.query_cone(269.45, 4.73, 0.08)
    assert s_status == "up"
    assert len(s_rows) == 1
    assert s_rows[0]["main_id"] == "Barnard's Star"

    gaia = GaiaAdapter(settings=settings, client=client)
    g_status, g_rows, truncated = await gaia.query_cone(269.45, 4.73, 0.08, epochs_mjd=[60900.0])
    assert g_status == "up"
    assert truncated is True  # hit gaia_max_rows=2
    assert "ra_epoch" in g_rows[0]

    # ADS without token -> not_configured
    ads = AdsAdapter(settings=settings, client=client)
    ads_status, ads_rows = await ads.search("Barnard's Star")
    assert ads_status == "not_configured"
    assert ads_rows == []

    # Instantiate remaining adapters cleanly
    _ = AllWiseAdapter(settings, client)
    _ = VizierAdapter(settings, client)
    _ = NedAdapter(settings, client)
    _ = CadcNeossatAdapter(settings, client)
    _ = HorizonsAdapter(settings, client)
    await client.aclose()
