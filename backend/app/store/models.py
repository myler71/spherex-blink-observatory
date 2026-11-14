from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SkyPatchORM(Base):
    __tablename__ = "sky_patches"

    patch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ra_deg: Mapped[float] = mapped_column(Float, nullable=False)
    dec_deg: Mapped[float] = mapped_column(Float, nullable=False)
    fov_deg: Mapped[float] = mapped_column(Float, nullable=False)
    constellation: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    pipeline_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_sky_patches_ra_dec", "ra_deg", "dec_deg"),)


class ObservationORM(Base):
    __tablename__ = "observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sky_patches.patch_id", ondelete="CASCADE"), nullable=False
    )
    query_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DetectedObjectORM(Base):
    __tablename__ = "detected_objects"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("observations.observation_id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ra_deg: Mapped[float] = mapped_column(Float, nullable=False)
    dec_deg: Mapped[float] = mapped_column(Float, nullable=False)
    pm_total_mas_yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_moving: Mapped[bool] = mapped_column(Boolean, default=False)
    is_variable: Mapped[bool] = mapped_column(Boolean, default=False)
    gaia_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ScientificDocumentORM(Base):
    __tablename__ = "scientific_documents"

    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    bibcode_or_doi: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    object_identifiers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    topic_category: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(title,'') || ' ' || chunk_text)", persisted=True),
    )
    embedding: Mapped[Any] = mapped_column(Vector(384), nullable=True)

    __table_args__ = (
        Index("ix_scientific_documents_tsv", "tsv", postgresql_using="gin"),
        Index("ix_scientific_documents_object_ids", "object_identifiers", postgresql_using="gin"),
    )


class NarrativeORM(Base):
    __tablename__ = "narratives"

    cache_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class BenchmarkRunORM(Base):
    __tablename__ = "benchmarks"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class CandidateORM(Base):
    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ra_deg: Mapped[float] = mapped_column(Float, nullable=False)
    dec_deg: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CandidateVoteORM(Base):
    __tablename__ = "candidate_votes"

    vote_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False
    )
    client_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    vote_label: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("candidate_id", "client_fingerprint", name="uq_candidate_voter"),
    )
