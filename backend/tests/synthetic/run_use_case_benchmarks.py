"""Run all six preset benchmark contracts on deterministic synthetic FITS inputs.

PYTHONPATH=backend python -m tests.synthetic.run_use_case_benchmarks --output docs/test-results/synthetic-benchmark.json
No real archive/catalog access, production Redis writes, or astrophysical discoveries.
"""

import argparse
import asyncio
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from app.jobs.run_benchmarks import run_benchmarks
from app.schemas.observe import ObserveQuery
from app.science.pipeline import ObservePipeline
from app.science.targets import list_target_presets
from app.store.cache import CacheStore
from tests.synthetic.fits_generator import generate_synthetic_dataset
from tests.synthetic.restorable_observation import (
    SyntheticArchiveAdapter,
    SyntheticCatalogAdapter,
    build_synthetic_scenario_for_target,
    create_isolated_test_settings,
)


async def run(output: Path) -> None:
    presets = {preset.id: preset for preset in list_target_presets()}
    inputs = {}
    observations = {}
    with tempfile.TemporaryDirectory(prefix="spherex-use-cases-") as tmp:
        settings = create_isolated_test_settings(tmp)

        class SyntheticPipeline:
            async def run(self, query: ObserveQuery):
                preset = presets[query.target]
                scenario = build_synthetic_scenario_for_target(preset)
                dataset = generate_synthetic_dataset(scenario, Path(tmp) / preset.id)
                inputs[preset.id] = {
                    "scenario": asdict(scenario),
                    "ground_truth": dataset.ground_truth,
                }
                # Target the known off-center variable injection, not a static
                # central source. Preserve the actual synthetic query below.
                if preset.expected_variable:
                    variable = dataset.ground_truth["variable"]
                    query = query.model_copy(update={"ra": variable["ra"], "dec": variable["dec"]})
                inputs[preset.id]["query"] = query.model_dump(mode="json")
                observation = await ObservePipeline(
                    settings,
                    archive=SyntheticArchiveAdapter(dataset),
                    catalogs=SyntheticCatalogAdapter(),
                ).run(query)
                observations[preset.id] = {
                    "selection": observation.selection.model_dump(mode="json"),
                    "objects": [
                        obj.model_dump(mode="json") for obj in observation.detected_objects
                    ],
                }
                return observation

        result = await run_benchmarks(
            settings,
            CacheStore(settings),
            pipeline=SyntheticPipeline(),
            data_source="synthetic",
        )
        payload = {
            "provenance": "Generated synthetic FITS with seed 42; mock archive/catalog adapters; not real sky measurements.",
            "qualification": "Benchmark evaluates the nearest-center detection. Variable cases query their known injected source position, documented in inputs.query. Fit uncertainties and synthetic signal recovery do not establish real target identity.",
            "inputs": inputs,
            "observations": observations,
            "benchmark": result.model_dump(mode="json"),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2))
        for item in result.results:
            print(
                f"{item.target_id}: {item.status}; {item.measured_value}; uncertainty={item.measured_uncertainty}"
            )
        if any(item.status != "pass" for item in result.results):
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
