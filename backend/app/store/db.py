from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.schemas.candidates import CandidateCreate, CandidateRecord, CandidateVoteCreate
from app.schemas.common import ServiceStatus
from app.store.documents import LocalDocumentStore
from app.store.models import CandidateORM, CandidateVoteORM, ScientificDocumentORM


class DatabaseStore:
    """Async PostgreSQL + pgvector store with graceful unavailability and local FTS5 fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.docs_fallback = LocalDocumentStore(Path(settings.cache_dir) / "local_docs.sqlite3")
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._in_memory_candidates: dict[str, dict[str, Any]] = {}
        try:
            self._engine = create_async_engine(
                settings.database_url,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 2},
            )
            self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        except Exception:
            self._engine = None
            self._sessionmaker = None

    async def check_health(self) -> ServiceStatus:
        if self._engine is None:
            return ServiceStatus(status="unavailable", detail="Database engine not initialized")
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return ServiceStatus(status="up")
        except Exception as exc:
            return ServiceStatus(status="unavailable", detail=str(exc)[:180])

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def search_documents(
        self,
        query: str,
        object_identifiers: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if self._sessionmaker is not None:
            try:
                async with self._sessionmaker() as session:
                    stmt = select(ScientificDocumentORM).limit(limit * 3)
                    rows = (await session.execute(stmt)).scalars().all()
                    if rows:
                        wanted = {x.lower() for x in (object_identifiers or [])}
                        q_terms = {t.lower() for t in query.split() if len(t) > 2}
                        scored: list[dict[str, Any]] = []
                        for r in rows:
                            id_hit = any(w in {i.lower() for i in r.object_identifiers} for w in wanted)
                            txt = f"{r.title} {r.chunk_text}".lower()
                            lex_hits = sum(1 for t in q_terms if t in txt)
                            if id_hit or lex_hits > 0:
                                scored.append(
                                    {
                                        "doc_id": r.doc_id,
                                        "title": r.title,
                                        "bibcode_or_doi": r.bibcode_or_doi,
                                        "source_url": r.source_url,
                                        "object_identifiers": list(r.object_identifiers),
                                        "topic_category": r.topic_category,
                                        "chunk_text": r.chunk_text,
                                        "score": (2.0 if id_hit else 0.0) + lex_hits,
                                    }
                                )
                        scored.sort(key=lambda item: -float(item["score"]))
                        if scored:
                            return scored[:limit]
            except Exception:
                pass
        return self.docs_fallback.search(query, object_identifiers=object_identifiers, limit=limit)

    async def create_candidate(self, payload: CandidateCreate) -> CandidateRecord:
        cid = f"cand_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(UTC).isoformat()
        if self._sessionmaker is not None:
            try:
                async with self._sessionmaker() as session:
                    row = CandidateORM(
                        candidate_id=cid,
                        observation_id=payload.observation_id,
                        object_id=payload.object_id,
                        ra_deg=payload.ra_deg,
                        dec_deg=payload.dec_deg,
                        reason=payload.reason,
                    )
                    session.add(row)
                    await session.commit()
                    return CandidateRecord(
                        candidate_id=cid,
                        observation_id=payload.observation_id,
                        object_id=payload.object_id,
                        ra_deg=payload.ra_deg,
                        dec_deg=payload.dec_deg,
                        reason=payload.reason,
                        created_at=now_iso,
                    )
            except Exception:
                pass

        self._in_memory_candidates[cid] = {
            "candidate_id": cid,
            "observation_id": payload.observation_id,
            "object_id": payload.object_id,
            "ra_deg": payload.ra_deg,
            "dec_deg": payload.dec_deg,
            "reason": payload.reason,
            "created_at": now_iso,
            "votes": {},
        }
        return CandidateRecord(
            candidate_id=cid,
            observation_id=payload.observation_id,
            object_id=payload.object_id,
            ra_deg=payload.ra_deg,
            dec_deg=payload.dec_deg,
            reason=payload.reason,
            created_at=now_iso,
        )

    async def list_candidates(self) -> list[CandidateRecord]:
        if self._sessionmaker is not None:
            try:
                async with self._sessionmaker() as session:
                    cands = (await session.execute(select(CandidateORM))).scalars().all()
                    votes = (await session.execute(select(CandidateVoteORM))).scalars().all()
                    by_cand: dict[str, dict[str, int]] = {}
                    for v in votes:
                        counts = by_cand.setdefault(v.candidate_id, {})
                        counts[v.vote_label] = counts.get(v.vote_label, 0) + 1
                    return [
                        self._to_record(
                            c.candidate_id,
                            c.observation_id,
                            c.object_id,
                            c.ra_deg,
                            c.dec_deg,
                            c.reason,
                            c.created_at.isoformat(),
                            by_cand.get(c.candidate_id, {}),
                        )
                        for c in cands
                    ]
            except Exception:
                pass

        out: list[CandidateRecord] = []
        for c in self._in_memory_candidates.values():
            counts: dict[str, int] = {}
            for lbl in c["votes"].values():
                counts[lbl] = counts.get(lbl, 0) + 1
            out.append(
                self._to_record(
                    c["candidate_id"],
                    c["observation_id"],
                    c["object_id"],
                    c["ra_deg"],
                    c["dec_deg"],
                    c["reason"],
                    c["created_at"],
                    counts,
                )
            )
        return out

    async def vote_candidate(
        self, candidate_id: str, vote: CandidateVoteCreate
    ) -> CandidateRecord | None:
        if self._sessionmaker is not None:
            try:
                async with self._sessionmaker() as session:
                    cand = await session.get(CandidateORM, candidate_id)
                    if cand is None:
                        return None
                    existing = (
                        await session.execute(
                            select(CandidateVoteORM).where(
                                CandidateVoteORM.candidate_id == candidate_id,
                                CandidateVoteORM.client_fingerprint == vote.client_fingerprint,
                            )
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        raise PermissionError("Duplicate vote for client fingerprint")
                    session.add(
                        CandidateVoteORM(
                            vote_id=f"vote_{uuid.uuid4().hex[:12]}",
                            candidate_id=candidate_id,
                            client_fingerprint=vote.client_fingerprint,
                            vote_label=vote.vote_label,
                        )
                    )
                    await session.commit()
                    all_cands = await self.list_candidates()
                    return next((x for x in all_cands if x.candidate_id == candidate_id), None)
            except PermissionError:
                raise
            except Exception:
                pass

        cand_mem = self._in_memory_candidates.get(candidate_id)
        if cand_mem is None:
            return None
        if vote.client_fingerprint in cand_mem["votes"]:
            raise PermissionError("Duplicate vote for client fingerprint")
        cand_mem["votes"][vote.client_fingerprint] = vote.vote_label
        all_cands = await self.list_candidates()
        return next((x for x in all_cands if x.candidate_id == candidate_id), None)

    @staticmethod
    def _to_record(
        candidate_id: str,
        observation_id: str,
        object_id: str,
        ra_deg: float,
        dec_deg: float,
        reason: str,
        created_at: str,
        counts: dict[str, int],
    ) -> CandidateRecord:
        total = sum(counts.values())
        consensus_label: str | None = None
        consensus_score = 0.0
        if total > 0:
            consensus_label = max(counts.items(), key=lambda item: item[1])[0]
            consensus_score = round(counts[consensus_label] / total, 3)
        return CandidateRecord(
            candidate_id=candidate_id,
            observation_id=observation_id,
            object_id=object_id,
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            reason=reason,
            created_at=created_at,
            vote_counts=counts,
            total_votes=total,
            consensus_label=consensus_label,
            consensus_score=consensus_score,
        )
