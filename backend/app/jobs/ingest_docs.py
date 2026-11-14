import asyncio
from typing import Any

from app.config import Settings, get_settings
from app.store.db import DatabaseStore

# License-safe SPHEREx mission & target summary chunks (NASA/IPAC public domain & metadata abstracts)
CORPUS_CHUNKS: list[dict[str, Any]] = [
    {
        "doc_id": "spherex_mission_overview",
        "title": "NASA SPHEREx All-Sky Spectral Survey Overview (DR1 & QR3)",
        "bibcode_or_doi": "10.26131/IRSA678",
        "source_url": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html",
        "object_identifiers": ["SPHEREx", "DR1", "QR3"],
        "topic_category": "mission_documentation",
        "chunk_text": (
            "SPHEREx maps the entire sky every six months in 102 near-infrared spectral channels "
            "from 0.75 to 5.0 micrometers across 6 Linear Variable Filter (LVF) detectors. "
            "DR1 and QR3 Level-2 MEFs include IMAGE, FLAGS, VARIANCE, ZODI, EPSF, and WCS-WAVE."
        ),
    },
    {
        "doc_id": "target_barnards_star",
        "title": "Barnard's Star Astrometry and Gaia DR3 Kinematics",
        "bibcode_or_doi": "Gaia DR3 4472832130942575872",
        "source_url": "https://gea.esac.esa.int/archive/",
        "object_identifiers": ["barnards_star", "Barnard's Star", "GJ 699"],
        "topic_category": "high_proper_motion",
        "chunk_text": (
            "Barnard's Star (GJ 699) is the fastest-moving star on the sky at ~10.39 arcsec/yr "
            "(pmra=-801.55 mas/yr, pmdec=+10362.39 mas/yr, parallax=546.98 mas in Gaia DR3)."
        ),
    },
    {
        "doc_id": "target_wise_0855",
        "title": "WISE J085510.83-071442.5 Coldest Known Y-Dwarf",
        "bibcode_or_doi": "2016AJ....152...78L",
        "source_url": "https://simbad.harvard.edu/simbad/sim-id?Ident=WISEA+J085510.74-071442.5",
        "object_identifiers": ["wise_0855", "WISE 0855", "WISEA J085510.74-071442.5"],
        "topic_category": "brown_dwarf",
        "chunk_text": (
            "WISE 0855 is a ~250 K Y2 brown dwarf at ~2.2 pc with proper motion ~8.15 arcsec/yr "
            "(pmra=-8123.7 mas/yr, pmdec=+673.2 mas/yr), faint in optical and brightest at 3-5 um."
        ),
    },
    {
        "doc_id": "target_epsilon_indi_b",
        "title": "Epsilon Indi Ba/Bb Binary Brown Dwarf System",
        "bibcode_or_doi": "2004A&A...413.1029M",
        "source_url": "https://simbad.harvard.edu/simbad/sim-id?Ident=*+eps+Ind+B",
        "object_identifiers": ["epsilon_indi_b", "Epsilon Indi B", "* eps Ind B"],
        "topic_category": "brown_dwarf",
        "chunk_text": (
            "Epsilon Indi B is a T1V+T6V binary brown dwarf companion to Epsilon Indi A "
            "with proper motion ~4.68 arcsec/yr (pmra=+3981.98 mas/yr, pmdec=-2466.83 mas/yr)."
        ),
    },
    {
        "doc_id": "target_rw_aurigae",
        "title": "RW Aurigae Classical T Tauri Infrared Variability",
        "bibcode_or_doi": "Gaia DR3 156430822114424576",
        "source_url": "https://simbad.harvard.edu/simbad/sim-id?Ident=V*+RW+Aur",
        "object_identifiers": ["rw_aurigae", "RW Aurigae", "V* RW Aur"],
        "topic_category": "variable_star",
        "chunk_text": (
            "RW Aurigae is a classical T Tauri variable star exhibiting irregular dimming and "
            "near-infrared variability due to circumstellar dust and accretion."
        ),
    },
    {
        "doc_id": "target_r_draconis",
        "title": "R Draconis Mira Long-Period Variable",
        "bibcode_or_doi": "Gaia DR3 1648328016354496384",
        "source_url": "https://simbad.harvard.edu/simbad/sim-id?Ident=V*+R+Dra",
        "object_identifiers": ["r_draconis", "R Draconis", "V* R Dra"],
        "topic_category": "variable_star",
        "chunk_text": (
            "R Draconis is a Mira-type long-period pulsating AGB variable star with strong "
            "infrared brightness modulation across multi-month baselines."
        ),
    },
    {
        "doc_id": "target_negative_control",
        "title": "Gaia DR3 720517945437337600 Static Non-Variable Control Star",
        "bibcode_or_doi": "Gaia DR3 720517945437337600",
        "source_url": "https://gea.esac.esa.int/archive/",
        "object_identifiers": ["negative_control", "Gaia DR3 720517945437337600"],
        "topic_category": "negative_control",
        "chunk_text": (
            "Gaia DR3 720517945437337600 is an isolated G=11.02 star with ruwe=0.886, "
            "|pm| < 1.6 mas/yr, and phot_variable_flag=NOT_AVAILABLE used as a static negative control."
        ),
    },
]


async def run_ingest_docs(settings: Settings, db: DatabaseStore) -> int:
    count = db.docs_fallback.upsert_chunks(CORPUS_CHUNKS)
    return count


def main() -> None:
    settings = get_settings()
    db = DatabaseStore(settings)
    n = asyncio.run(run_ingest_docs(settings, db))
    print(f"Ingested {n} license-safe scientific document chunks into {db.docs_fallback.db_path}")


if __name__ == "__main__":
    main()
