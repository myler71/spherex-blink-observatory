from pathlib import Path

import pytest

from app.config import Settings
from app.schemas.observe import ObserveQuery
from app.store.cache import CacheStore
from app.store.db import DatabaseStore
from app.store.documents import LocalDocumentStore


def test_cache_store_disk_fallback_and_version_invalidation(tmp_path: Path) -> None:
    s1 = Settings(cache_dir=str(tmp_path / "cache"), redis_url="redis://127.0.0.1:6599/0", pipeline_version="1.0.0")
    c1 = CacheStore(s1)
    q = ObserveQuery(ra=10.0, dec=20.0, fov=0.08)
    c1.set_json("observe", "k1", {"hello": "world"}, ttl_seconds=60)
    hit = c1.get_json("observe", "k1")
    assert hit is not None
    assert hit["hello"] == "world"

    # Different pipeline_version misses when keyed with version
    s2 = Settings(cache_dir=str(tmp_path / "cache"), redis_url="redis://127.0.0.1:6599/0", pipeline_version="2.0.0")
    c2 = CacheStore(s2)
    assert c2.get_json("observe", c2.versioned_key("k1")) is None
    assert q.ra == 10.0


def test_local_document_store_hybrid_lexical_retrieval(tmp_path: Path) -> None:
    docs = LocalDocumentStore(tmp_path / "docs.db")
    docs.upsert_chunks(
        [
            {
                "doc_id": "doc_wise0855_1",
                "title": "Cold Brown Dwarf WISE 0855",
                "bibcode_or_doi": "2016AJ....152...78L",
                "source_url": "https://ui.adsabs.harvard.edu/abs/2016AJ....152...78L",
                "object_identifiers": ["wise_0855", "WISE 0855"],
                "topic_category": "brown_dwarf",
                "chunk_text": "WISE J085510.83-071442.5 is the coldest known Y-type brown dwarf at ~250 K with high proper motion.",
            },
            {
                "doc_id": "doc_rwaur_1",
                "title": "RW Aurigae Outbursts",
                "bibcode_or_doi": "2018ApJ...864...45G",
                "source_url": "https://ui.adsabs.harvard.edu/abs/2018ApJ...864...45G",
                "object_identifiers": ["rw_aurigae", "RW Aurigae"],
                "topic_category": "variable_star",
                "chunk_text": "RW Aurigae is a classical T Tauri variable star exhibiting irregular dimming events.",
            },
        ]
    )
    res = docs.search("brown dwarf proper motion", object_identifiers=["wise_0855"], limit=5)
    assert len(res) >= 1
    assert res[0]["doc_id"] == "doc_wise0855_1"


@pytest.mark.asyncio
async def test_database_store_degrades_gracefully_when_postgres_absent(tmp_path: Path) -> None:
    s = Settings(
        database_url="postgresql+psycopg://invalid:invalid@127.0.0.1:6598/none",
        cache_dir=str(tmp_path / "cache"),
    )
    db = DatabaseStore(s)
    status = await db.check_health()
    assert status.status == "unavailable"
    await db.close()
