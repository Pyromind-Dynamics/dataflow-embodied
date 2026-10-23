"""Create an artificial S2 fixture and validate a complete offline export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cleaning import EmbodiedCleaningPipeline, finalize_dataset


def run(output_dir):
    from ..core.fixture import create_fixture
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = create_fixture(output)
    spec = {"path": str(source), "task_text": "Move an artificial fixture object",
            "confirm_subtasks": True, "confirm_derived_action": True}
    manifest = output / "input.jsonl"
    manifest.write_text(json.dumps({"episode": spec}) + "\n")
    pipeline = EmbodiedCleaningPipeline(manifest, output / "run", idle_min_duration_s=10)
    pipeline.compile()
    pipeline.forward()
    rows = [json.loads(x) for x in (output / "run/steps/embodied_step2.jsonl").read_text().splitlines()]
    merged = finalize_dataset([x["episode_export"] for x in rows], output / "dataset", task_text=spec["task_text"])
    summary = {"demo_only": True, "episode_count": merged["validation"]["episode_count"],
               "frame_count": merged["validation"]["frame_count"],
               "valid": merged["validation"]["valid"], "dataset_path": merged["dataset_path"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new output directory")
    print(json.dumps(run(parser.parse_args().output)))
