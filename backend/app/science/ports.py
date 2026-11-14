from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ArchiveObservationMeta:
    obs_id: str
    plane_id: str
    collection: str
    mjd_start: float
    mjd_end: float
    bandpass: str
    provenance_version: str
    raw_uri: str
    cutout_url: str


@dataclass(frozen=True)
class CutoutFetchResult:
    obs_id: str
    archive_url: str
    local_path: Path | None
    error: str | None = None


class ArchivePort(Protocol):
    async def search_observations(
        self,
        ra_deg: float,
        dec_deg: float,
        releases: list[str] | None = None,
    ) -> list[ArchiveObservationMeta]: ...

    async def fetch_cutouts(
        self,
        observations: list[ArchiveObservationMeta],
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
    ) -> list[CutoutFetchResult]: ...


class CatalogOverlayPort(Protocol):
    async def query_all(
        self,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        epochs_mjd: list[float],
        include_neossat: bool = False,
        include_horizons: bool = False,
    ) -> dict[str, Any]: ...
