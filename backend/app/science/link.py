from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from app.config import Settings
from app.science.align import AlignedFrame
from app.science.detect import FrameDetection


@dataclass
class LinkedTrack:
    track_id: str
    observations: list[FrameDetection] = field(default_factory=list)
    mean_ra: float = 0.0
    mean_dec: float = 0.0
    mean_x: float = 0.0
    mean_y: float = 0.0
    mean_snr: float = 0.0
    contaminated: bool = False


def _radec_to_unitvec(ra_deg: float, dec_deg: float) -> np.ndarray:
    ra_r = np.deg2rad(ra_deg)
    dec_r = np.deg2rad(dec_deg)
    c_dec = np.cos(dec_r)
    return np.array(
        [c_dec * np.cos(ra_r), c_dec * np.sin(ra_r), np.sin(dec_r)],
        dtype=np.float64,
    )


def _ang_sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    v1 = _radec_to_unitvec(ra1, dec1)
    v2 = _radec_to_unitvec(ra2, dec2)
    dot = float(np.clip(np.dot(v1, v2), -1.0, 1.0))
    return float(np.rad2deg(np.arccos(dot)) * 3600.0)


def link_detections(
    per_frame_detections: list[list[FrameDetection]],
    frames: list[AlignedFrame],
    settings: Settings,
) -> list[LinkedTrack]:
    """Progressive multi-epoch source linking across ALL frames via spherical 3D cKDTree."""
    # Order frames chronologically so track centroids evolve smoothly across epochs
    indexed_frames = sorted(
        enumerate(zip(frames, per_frame_detections, strict=False)),
        key=lambda item: float(item[1][0].mjd or 0.0),
    )

    chord_radius = 2.0 * np.sin(np.deg2rad(settings.match_radius_arcsec / 3600.0) / 2.0)
    tracks: list[LinkedTrack] = []

    for _, (frame, dets) in indexed_frames:
        if not dets:
            continue
        if not tracks:
            for det in dets:
                tracks.append(
                    LinkedTrack(
                        track_id=f"obj_{len(tracks) + 1:03d}",
                        observations=[det],
                        mean_ra=det.ra,
                        mean_dec=det.dec,
                        mean_x=det.x,
                        mean_y=det.y,
                        mean_snr=det.snr,
                        contaminated=det.contaminated,
                    )
                )
            continue

        track_vecs = np.array([_radec_to_unitvec(t.mean_ra, t.mean_dec) for t in tracks])
        tree = cKDTree(track_vecs)

        tight_radius = min(4.0, settings.match_radius_arcsec)
        assigned_dets: set[int] = set()
        assigned_tracks: set[int] = set()

        for pass_radius in (tight_radius, settings.match_radius_arcsec):
            candidate_pairs: list[tuple[float, int, int]] = []
            for det_idx, det in enumerate(dets):
                if det_idx in assigned_dets:
                    continue
                dv = _radec_to_unitvec(det.ra, det.dec)
                nearby = tree.query_ball_point(dv, r=chord_radius)
                for tr_idx in nearby:
                    if tr_idx in assigned_tracks:
                        continue
                    sep_as = _ang_sep_arcsec(
                        det.ra, det.dec, tracks[tr_idx].mean_ra, tracks[tr_idx].mean_dec
                    )
                    if sep_as <= pass_radius:
                        candidate_pairs.append((sep_as, det_idx, tr_idx))

            candidate_pairs.sort(key=lambda item: item[0])
            for _, det_idx, tr_idx in candidate_pairs:
                if det_idx in assigned_dets or tr_idx in assigned_tracks:
                    continue
                if any(o.obs_id == frame.obs_id for o in tracks[tr_idx].observations):
                    continue
                assigned_dets.add(det_idx)
                assigned_tracks.add(tr_idx)
                tr = tracks[tr_idx]
                tr.observations.append(dets[det_idx])
                tr.mean_ra = float(np.mean([o.ra for o in tr.observations]))
                tr.mean_dec = float(np.mean([o.dec for o in tr.observations]))
                tr.mean_x = float(np.mean([o.x for o in tr.observations]))
                tr.mean_y = float(np.mean([o.y for o in tr.observations]))
                tr.mean_snr = float(np.mean([o.snr for o in tr.observations]))
                tr.contaminated = any(o.contaminated for o in tr.observations)
        for det_idx, det in enumerate(dets):
            if det_idx not in assigned_dets:
                tracks.append(
                    LinkedTrack(
                        track_id=f"obj_{len(tracks) + 1:03d}",
                        observations=[det],
                        mean_ra=det.ra,
                        mean_dec=det.dec,
                        mean_x=det.x,
                        mean_y=det.y,
                        mean_snr=det.snr,
                        contaminated=det.contaminated,
                    )
                )

    return tracks
