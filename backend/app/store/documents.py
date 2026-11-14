import json
import re
import sqlite3
from pathlib import Path
from typing import Any


class LocalDocumentStore:
    """Zero-dependency SQLite FTS5 lexical + metadata store for offline RAG fallback (FR-31)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS docs (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    bibcode_or_doi TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    object_identifiers TEXT NOT NULL,
                    topic_category TEXT NOT NULL,
                    chunk_text TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
                    doc_id UNINDEXED,
                    title,
                    chunk_text,
                    object_identifiers
                )
                """
            )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        with self._connect() as conn:
            for c in chunks:
                ids_json = json.dumps(c.get("object_identifiers", []))
                ids_text = " ".join(c.get("object_identifiers", []))
                conn.execute(
                    """
                    INSERT INTO docs (doc_id, title, bibcode_or_doi, source_url, object_identifiers, topic_category, chunk_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        title=excluded.title,
                        bibcode_or_doi=excluded.bibcode_or_doi,
                        source_url=excluded.source_url,
                        object_identifiers=excluded.object_identifiers,
                        topic_category=excluded.topic_category,
                        chunk_text=excluded.chunk_text
                    """,
                    (
                        c["doc_id"],
                        c["title"],
                        c["bibcode_or_doi"],
                        c["source_url"],
                        ids_json,
                        c.get("topic_category", "general"),
                        c["chunk_text"],
                    ),
                )
                conn.execute("DELETE FROM docs_fts WHERE doc_id = ?", (c["doc_id"],))
                conn.execute(
                    "INSERT INTO docs_fts (doc_id, title, chunk_text, object_identifiers) VALUES (?, ?, ?, ?)",
                    (c["doc_id"], c["title"], c["chunk_text"], ids_text),
                )
        return len(chunks)

    def search(
        self,
        query: str,
        object_identifiers: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        fts_expr = " OR ".join(f'"{t}"' for t in tokens[:12]) if tokens else '"SPHEREx"'
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*, bm25(docs_fts) AS rank_score
                FROM docs_fts f
                JOIN docs d ON f.doc_id = d.doc_id
                WHERE docs_fts MATCH ?
                ORDER BY rank_score ASC
                LIMIT ?
                """,
                (fts_expr, limit * 3),
            ).fetchall()

            results: list[dict[str, Any]] = []
            wanted = {s.lower() for s in (object_identifiers or [])}
            for r in rows:
                ids = json.loads(r["object_identifiers"])
                id_match = any(w in {x.lower() for x in ids} for w in wanted) if wanted else False
                results.append(
                    {
                        "doc_id": r["doc_id"],
                        "title": r["title"],
                        "bibcode_or_doi": r["bibcode_or_doi"],
                        "source_url": r["source_url"],
                        "object_identifiers": ids,
                        "topic_category": r["topic_category"],
                        "chunk_text": r["chunk_text"],
                        "score": (1.0 if id_match else 0.0) + max(0.0, -float(r["rank_score"])),
                        "id_match": id_match,
                    }
                )
            # Also include direct object_identifier matches even if query keywords missed
            if wanted and len(results) < limit:
                all_rows = conn.execute("SELECT * FROM docs").fetchall()
                seen = {x["doc_id"] for x in results}
                for r in all_rows:
                    if r["doc_id"] in seen:
                        continue
                    ids = json.loads(r["object_identifiers"])
                    if any(w in {x.lower() for x in ids} for w in wanted):
                        results.append(
                            {
                                "doc_id": r["doc_id"],
                                "title": r["title"],
                                "bibcode_or_doi": r["bibcode_or_doi"],
                                "source_url": r["source_url"],
                                "object_identifiers": ids,
                                "topic_category": r["topic_category"],
                                "chunk_text": r["chunk_text"],
                                "score": 1.5,
                                "id_match": True,
                            }
                        )
            results.sort(key=lambda item: (-int(item["id_match"]), -float(item["score"])))
            return results[:limit]
