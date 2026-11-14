from astropy.io import fits
import numpy as np

from app.schemas.observe import FlagSummary

# Verified in V-06 from live DR1/QR3 FITS headers (MSKN* / MSKD*)
VERIFIED_FLAG_BITS: dict[int, tuple[str, str]] = {
    0: ("TRANSIENT", "Transient detected during SUR"),
    1: ("OVERFLOW", "Overflow detected during SUR"),
    2: ("SUR_ERROR", "Error in onboard processing"),
    6: ("NONFUNC", "Permanently unusable"),
    7: ("DICHROIC", "Low efficiency due to dichroic"),
    9: ("MISSING_DATA", "Onboard data lost"),
    10: ("HOT", "Hot pixel"),
    11: ("COLD", "Anomalously low signal"),
    12: ("FULLSAMPLE", "Pixel full sample history is available"),
    14: ("PHANMISS", "Phantom correction was not applied"),
    15: ("NONLINEAR", "Nonlinearity correction cannot be applied reliably"),
    17: ("PERSIST", "Persistent charge above threshold"),
    19: ("OUTLIER", "Pixel flagged by Detect Outliers"),
    20: ("CROSSTALK", "Pixel affected by crosstalk."),
    21: ("SOURCE", "Pixel mapped to a known source"),
    22: ("GHOST", "Affected by a bright source inside the exposure"),
    23: ("GHOST_FPA", "Affected by a bright source on another detector"),
    24: ("GHOST_EXT", "Pixel affected by a bright source outside FOV"),
    25: ("STREAK", "Pixel affected by a streak"),
    26: ("BLOOM", "Pixel part of a bloom artifact"),
    27: ("SNOWBALL", "Pixel part of a snowball artifact"),
    28: ("HALO", "Pixel part of a transient halo"),
}

# Wire uint8 mask bits
MASK_BIT_REJECTED = 1 << 0
MASK_BIT_OUT_OF_BOUNDS = 1 << 1
MASK_BIT_SOURCE = 1 << 2
MASK_BIT_GHOST_HALO = 1 << 3
MASK_BIT_DICHROIC_CROSSTALK = 1 << 4


def parse_flag_definitions(flags_header: fits.Header | None) -> dict[int, tuple[str, str]]:
    defs = dict(VERIFIED_FLAG_BITS)
    if flags_header is None:
        return defs
    for key in flags_header.keys():
        if key.startswith("MSKN") and key[4:].isdigit():
            bit = int(key[4:])
            desc_key = "MSKD" + key[4:]
            defs[bit] = (str(flags_header[key]), str(flags_header.get(desc_key, "")))
    return defs


def build_flag_mask_and_summary(
    flags_array: np.ndarray,
    reject_bits: list[int],
    flags_header: fits.Header | None = None,
) -> tuple[np.ndarray, np.ndarray, FlagSummary]:
    """Decode uint32 FLAGS into boolean reject mask, packed uint8 wire mask, and provenance summary."""
    uflags = np.asarray(flags_array, dtype=np.uint32)
    defs = parse_flag_definitions(flags_header)

    reject_bitmask = np.uint32(0)
    for b in reject_bits:
        if 0 <= b < 32:
            reject_bitmask |= np.uint32(1 << b)

    bad_mask = (uflags & reject_bitmask) != 0
    total_px = int(uflags.size)
    rejected_px = int(np.count_nonzero(bad_mask))

    bit_counts: dict[str, int] = {}
    bit_descriptions: dict[str, str] = {}
    for bit, (name, desc) in sorted(defs.items()):
        cnt = int(np.count_nonzero((uflags & np.uint32(1 << bit)) != 0))
        if cnt > 0:
            bit_counts[name] = cnt
            bit_descriptions[name] = desc

    u8 = np.zeros(uflags.shape, dtype=np.uint8)
    u8[bad_mask] |= MASK_BIT_REJECTED
    u8[(uflags & np.uint32(1 << 21)) != 0] |= MASK_BIT_SOURCE
    ghost_mask = np.uint32((1 << 22) | (1 << 23) | (1 << 24) | (1 << 28))
    u8[(uflags & ghost_mask) != 0] |= MASK_BIT_GHOST_HALO
    caution_mask = np.uint32((1 << 7) | (1 << 14) | (1 << 20))
    u8[(uflags & caution_mask) != 0] |= MASK_BIT_DICHROIC_CROSSTALK

    summary = FlagSummary(
        total_pixels=total_px,
        rejected_pixels=rejected_px,
        fraction_rejected=(rejected_px / total_px) if total_px > 0 else 0.0,
        bit_counts=bit_counts,
        bit_descriptions=bit_descriptions,
    )
    return bad_mask, u8, summary
