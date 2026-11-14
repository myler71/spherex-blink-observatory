from typing import Any

from app.schemas.narrative import EvidenceItem, EvidenceStoreResponse
from app.schemas.observe import ObserveResponse


class EvidenceBuilder:
    """Builds a deterministic, stable-ID EvidenceStoreResponse from ObserveResponse + retrieved docs."""

    def build(
        self,
        observe: ObserveResponse,
        docs: list[dict[str, Any]] | None = None,
        ads_papers: list[dict[str, Any]] | None = None,
    ) -> EvidenceStoreResponse:
        items: list[EvidenceItem] = []

        # 1. Patch-level observation metadata
        first_frame = observe.frames[0] if observe.frames else None
        items.append(
            EvidenceItem(
                evidence_id="ev_patch_001",
                evidence_type="observation_metadata",
                source_name="NASA SPHEREx",
                source_type="NASA SPHEREx",
                reference_id=first_frame.obs_id if first_frame else observe.observation_id,
                url=(
                    first_frame.provenance.archive_url
                    if first_frame
                    else "https://irsa.ipac.caltech.edu/Missions/spherex.html"
                ),
                object_id=None,
                fact_payload={
                    "ra_deg": observe.query.ra,
                    "dec_deg": observe.query.dec,
                    "fov_deg": observe.query.fov,
                    "constellation": observe.constellation,
                    "selected_frames": observe.selection.selected_count,
                    "visits_count": observe.selection.visits_count,
                    "baseline_days": observe.selection.baseline_days,
                },
            )
        )

        # 2. Deterministic pipeline object measurements & catalog links
        for idx, obj in enumerate(observe.detected_objects[:20], start=1):
            payload: dict[str, Any] = {
                "ra_deg": obj.ra,
                "dec_deg": obj.dec,
                "snr": obj.snr,
                "n_detections": obj.n_detections,
                "is_candidate_moving": obj.is_candidate_moving,
                "is_variable": obj.is_variable,
                "gaia_status": obj.gaia_counterpart.status,
            }
            if obj.motion.pm_total_arcsec_yr is not None:
                payload["pm_total_arcsec_yr"] = obj.motion.pm_total_arcsec_yr
                payload["pm_total_mas_yr"] = obj.motion.pm_total_mas_yr
                payload["significance_sigma"] = obj.motion.significance_sigma
                if obj.motion.pm_total_err_mas_yr is not None:
                    payload["pm_total_err_arcsec_yr"] = round(
                        obj.motion.pm_total_err_mas_yr / 1000.0, 4
                    )
            if obj.variability:
                max_chi2 = max(
                    (b.reduced_chi2 for b in obj.variability if b.reduced_chi2 is not None),
                    default=None,
                )
                if max_chi2 is not None:
                    payload["max_reduced_chi2"] = max_chi2

            items.append(
                EvidenceItem(
                    evidence_id=f"ev_det_{idx:03d}",
                    evidence_type="measurement",
                    source_name="NASA SPHEREx Pipeline",
                    source_type="NASA SPHEREx",
                    reference_id=obj.id,
                    url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                    object_id=obj.id,
                    fact_payload=payload,
                )
            )

            if obj.gaia_counterpart.status == "has_counterpart" and obj.gaia_counterpart.source_id:
                items.append(
                    EvidenceItem(
                        evidence_id=f"ev_gaia_{idx:03d}",
                        evidence_type="catalogue_entry",
                        source_name="ESA Gaia DR3",
                        source_type="ESA Gaia DR3",
                        reference_id=f"Gaia DR3 {obj.gaia_counterpart.source_id}",
                        url="https://gea.esac.esa.int/archive/",
                        object_id=obj.id,
                        fact_payload={
                            "source_id": obj.gaia_counterpart.source_id,
                            "separation_arcsec": obj.gaia_counterpart.separation_arcsec,
                            "pmra_mas_yr": obj.gaia_counterpart.pmra_mas_yr,
                            "pmdec_mas_yr": obj.gaia_counterpart.pmdec_mas_yr,
                            "phot_g_mean_mag": obj.gaia_counterpart.phot_g_mean_mag,
                        },
                    )
                )

            for m_idx, match in enumerate(obj.catalog_matches[:3], start=1):
                stype = (
                    "AllWISE Catalog"
                    if match.catalog == "AllWISE"
                    else "SIMBAD Catalog"
                )
                items.append(
                    EvidenceItem(
                        evidence_id=f"ev_cat_{idx:03d}_{m_idx}",
                        evidence_type="catalogue_entry",
                        source_name=match.catalog,
                        source_type=stype,
                        reference_id=match.identifier,
                        url=match.url or "https://simbad.harvard.edu/",
                        object_id=obj.id,
                        fact_payload={
                            "identifier": match.identifier,
                            "otype": match.otype,
                            "separation_arcsec": match.separation_arcsec,
                        },
                    )
                )

        # 3. Local & ADS papers
        for p_idx, doc in enumerate((docs or [])[:6], start=1):
            items.append(
                EvidenceItem(
                    evidence_id=f"ev_doc_{p_idx:03d}",
                    evidence_type="paper",
                    source_name=str(doc.get("title") or "SPHEREx Literature"),
                    source_type="Peer-Reviewed Paper",
                    reference_id=str(doc.get("bibcode_or_doi") or doc.get("doc_id") or "SPHEREx"),
                    url=str(doc.get("source_url") or "https://irsa.ipac.caltech.edu/Missions/spherex.html"),
                    object_id=None,
                    fact_payload={"title": doc.get("title"), "topic": doc.get("topic_category")},
                )
            )

        for a_idx, paper in enumerate((ads_papers or [])[:5], start=1):
            bib = str(paper.get("bibcode") or f"ADS_{a_idx}")
            items.append(
                EvidenceItem(
                    evidence_id=f"ev_ads_{a_idx:03d}",
                    evidence_type="paper",
                    source_name=str(paper.get("title") or bib),
                    source_type="Peer-Reviewed Paper",
                    reference_id=str(paper.get("doi") or bib),
                    url=str(paper.get("url") or f"https://ui.adsabs.harvard.edu/abs/{bib}"),
                    object_id=None,
                    fact_payload={"year": paper.get("year"), "bibcode": bib},
                )
            )

        return EvidenceStoreResponse(
            observation_id=observe.observation_id,
            pipeline_version=observe.pipeline_version,
            items=items,
        )
