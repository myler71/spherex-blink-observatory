"""Initial SPHEREx schema with pgvector and tsvector indexes.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-14
"""
from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sky_patches",
        sa.Column("patch_id", sa.String(64), primary_key=True),
        sa.Column("target_name", sa.String(200), nullable=True),
        sa.Column("ra_deg", sa.Float, nullable=False),
        sa.Column("dec_deg", sa.Float, nullable=False),
        sa.Column("fov_deg", sa.Float, nullable=False),
        sa.Column("constellation", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(32), nullable=False),
        sa.Column("pipeline_payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sky_patches_ra_dec", "sky_patches", ["ra_deg", "dec_deg"])

    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column(
            "patch_id",
            sa.String(64),
            sa.ForeignKey("sky_patches.patch_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("payload_json", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "detected_objects",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "observation_id",
            sa.String(64),
            sa.ForeignKey("observations.observation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("ra_deg", sa.Float, nullable=False),
        sa.Column("dec_deg", sa.Float, nullable=False),
        sa.Column("pm_total_mas_yr", sa.Float, nullable=True),
        sa.Column("is_moving", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_variable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("gaia_status", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "scientific_documents",
        sa.Column("doc_id", sa.String(128), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("bibcode_or_doi", sa.String(128), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("object_identifiers", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("topic_category", sa.String(64), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR,
            sa.Computed(
                "to_tsvector('english', coalesce(title,'') || ' ' || chunk_text)",
                persisted=True,
            ),
        ),
        sa.Column("embedding", Vector(384), nullable=True),
    )
    op.create_index("ix_scientific_documents_tsv", "scientific_documents", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_scientific_documents_object_ids",
        "scientific_documents",
        ["object_identifiers"],
        postgresql_using="gin",
    )

    op.create_table(
        "narratives",
        sa.Column("cache_key", sa.String(256), primary_key=True),
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(32), nullable=False),
        sa.Column("provider_mode", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "benchmarks",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", postgresql.JSONB, nullable=False),
    )

    op.create_table(
        "candidates",
        sa.Column("candidate_id", sa.String(64), primary_key=True),
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("ra_deg", sa.Float, nullable=False),
        sa.Column("dec_deg", sa.Float, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "candidate_votes",
        sa.Column("vote_id", sa.String(64), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(64),
            sa.ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_fingerprint", sa.String(128), nullable=False),
        sa.Column("vote_label", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("candidate_id", "client_fingerprint", name="uq_candidate_voter"),
    )


def downgrade() -> None:
    op.drop_table("candidate_votes")
    op.drop_table("candidates")
    op.drop_table("benchmarks")
    op.drop_table("narratives")
    op.drop_index("ix_scientific_documents_object_ids", table_name="scientific_documents")
    op.drop_index("ix_scientific_documents_tsv", table_name="scientific_documents")
    op.drop_table("scientific_documents")
    op.drop_table("detected_objects")
    op.drop_table("observations")
    op.drop_index("ix_sky_patches_ra_dec", table_name="sky_patches")
    op.drop_table("sky_patches")
