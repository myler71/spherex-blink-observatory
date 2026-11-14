from dataclasses import dataclass

from app.config import Settings
from app.science.ports import ArchiveObservationMeta

# Nominal detector wavelength ranges from V-01/A5 (micrometers)
DETECTOR_WAVELENGTH_RANGES: dict[int, tuple[float, float]] = {
    1: (0.75, 1.09),
    2: (1.10, 1.62),
    3: (1.63, 2.41),
    4: (2.42, 3.82),
    5: (3.83, 4.41),
    6: (4.42, 5.00),
}


def detector_from_bandpass(bandpass: str) -> int | None:
    text = bandpass.upper()
    for det in range(1, 7):
        if f"D{det}" in text:
            return det
    return None


@dataclass(frozen=True)
class SelectionResult:
    selected: list[ArchiveObservationMeta]
    total_candidates: int
    visits_count: int
    wavelength_bins_count: int
    matching_tolerance_um: float
    baseline_days: float
    single_visit_warning: str | None = None


def _release_priority(collection: str, configured: list[str]) -> int:
    try:
        return configured.index(collection)
    except ValueError:
        return len(configured) + 1


def select_observations(
    candidates: list[ArchiveObservationMeta],
    max_frames: int,
    settings: Settings,
    detector: int | None = None,
    wave_min: float | None = None,
    wave_max: float | None = None,
) -> SelectionResult:
    """Deduplicate exposures across releases, cluster visits, and maximize time baseline with band match."""
    if not candidates:
        return SelectionResult(
            selected=[],
            total_candidates=0,
            visits_count=0,
            wavelength_bins_count=0,
            matching_tolerance_um=0.02,
            baseline_days=0.0,
            single_visit_warning="No observations available.",
        )

    # Deduplicate same obs_id across releases (prefer DR1/configured order, V-02)
    by_obs: dict[str, ArchiveObservationMeta] = {}
    for item in candidates:
        det = detector_from_bandpass(item.bandpass)
        if detector is not None and det != detector:
            continue
        if (wave_min is not None or wave_max is not None) and det is not None:
            d_lo, d_hi = DETECTOR_WAVELENGTH_RANGES[det]
            if wave_min is not None and d_hi < wave_min:
                continue
            if wave_max is not None and d_lo > wave_max:
                continue
        existing = by_obs.get(item.obs_id)
        if existing is None or _release_priority(
            item.collection, settings.spherex_releases
        ) < _release_priority(existing.collection, settings.spherex_releases):
            by_obs[item.obs_id] = item

    deduped = sorted(by_obs.values(), key=lambda x: x.mjd_start)
    if not deduped:
        return SelectionResult(
            selected=[],
            total_candidates=len(candidates),
            visits_count=0,
            wavelength_bins_count=0,
            matching_tolerance_um=0.02,
            baseline_days=0.0,
            single_visit_warning="No observations match detector/wavelength filters.",
        )

    # Cluster into visits separated by > visit_gap_days
    visits: list[list[ArchiveObservationMeta]] = []
    for item in deduped:
        if not visits or (item.mjd_start - visits[-1][-1].mjd_end) > settings.visit_gap_days:
            visits.append([item])
        else:
            visits[-1].append(item)

    # Prioritize bandpasses that appear in the widest span of visits, then spread across visits
    band_visits: dict[str, set[int]] = {}
    for v_idx, v_items in enumerate(visits):
        for it in v_items:
            band_visits.setdefault(it.bandpass, set()).add(v_idx)

    # Sort visits to sample earliest, latest, and intermediate evenly
    visit_order: list[int] = []
    if len(visits) == 1:
        visit_order = [0]
    else:
        visit_order = [0, len(visits) - 1]
        for idx in range(1, len(visits) - 1):
            visit_order.append(idx)

    # Prefer matched bandpasses spanning >= 2 visits
    matched_bands = sorted(
        band_visits.keys(),
        key=lambda b: (-len(band_visits[b]), b),
    )

    selected: list[ArchiveObservationMeta] = []
    seen_ids: set[str] = set()

    # Round-robin across visits and matched bands so widest baseline is always represented
    for band in matched_bands:
        if len(selected) >= max_frames:
            break
        for v_idx in visit_order:
            if len(selected) >= max_frames:
                break
            for it in visits[v_idx]:
                if it.bandpass == band and it.obs_id not in seen_ids:
                    selected.append(it)
                    seen_ids.add(it.obs_id)
                    break

    # Fill any remaining budget chronologically
    if len(selected) < max_frames:
        for v_idx in visit_order:
            for it in visits[v_idx]:
                if len(selected) >= max_frames:
                    break
                if it.obs_id not in seen_ids:
                    selected.append(it)
                    seen_ids.add(it.obs_id)

    selected.sort(key=lambda x: x.mjd_start)
    sel_mjds = [x.mjd_start for x in selected]
    baseline = float(max(sel_mjds) - min(sel_mjds)) if len(sel_mjds) >= 2 else 0.0

    # Recompute distinct visits among selected frames
    sel_visits = 0
    prev_mjd: float | None = None
    for m in sel_mjds:
        if prev_mjd is None or (m - prev_mjd) > settings.visit_gap_days:
            sel_visits += 1
        prev_mjd = m

    warning = None
    if sel_visits < 2:
        warning = (
            f"Only {sel_visits} visit covered by selected frames (baseline={baseline:.2f} d); "
            "proper motion cannot be separated."
        )

    bins_count = len({s.bandpass for s in selected})
    # Typical local bandwidth fraction default (~0.025 um at R~40)
    nominal_tol = round(0.04 * settings.band_match_fraction, 4)

    return SelectionResult(
        selected=selected,
        total_candidates=len(deduped),
        visits_count=sel_visits,
        wavelength_bins_count=bins_count,
        matching_tolerance_um=nominal_tol,
        baseline_days=round(baseline, 4),
        single_visit_warning=warning,
    )
