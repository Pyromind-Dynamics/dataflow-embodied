from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow_embodied import (EmbodiedDatasetInspector, EmbodiedCleaningPlanner,
                              EmbodiedLeRobotExporter, EmbodiedDatasetValidator)
from dataflow_embodied.pipelines.cleaning import EmbodiedCleaningPipeline, finalize_dataset

pytestmark = [pytest.mark.cpu, pytest.mark.media]


def episode_spec(path):
    return {"path": str(path), "task_text": "Move the fixture object", "confirm_subtasks": True,
            "confirm_derived_action": True}


def test_registration_and_no_optional_media_import_on_package_import():
    assert OPERATOR_REGISTRY.get("EmbodiedCleaningPlanner") is EmbodiedCleaningPlanner
    assert OPERATOR_REGISTRY.get("EmbodiedLeRobotExporter") is EmbodiedLeRobotExporter


def test_inspection_and_planning_are_read_only(self_collected_path):
    before = {str(p): p.read_bytes() for p in self_collected_path.rglob("*") if p.is_file()}
    spec = episode_spec(self_collected_path)
    inspection = EmbodiedDatasetInspector().transform(spec)
    planned = EmbodiedCleaningPlanner(idle_min_duration_s=10).transform(spec)
    assert inspection["inspection"]["episode_count"] == 1
    assert planned["status"] == "planned"
    assert planned["plan"]["timeline_mapping"]
    assert {str(p): p.read_bytes() for p in self_collected_path.rglob("*") if p.is_file()} == before


def test_pipeline_exports_and_dataset_finalization_validates_frames(self_collected_path, tmp_path):
    inputs = tmp_path / "manifest.jsonl"
    inputs.write_text(json.dumps({"episode": episode_spec(self_collected_path)}) + "\n")
    pipeline = EmbodiedCleaningPipeline(inputs, tmp_path / "run", idle_min_duration_s=10)
    pipeline.compile()
    pipeline.forward()
    frames = [pd.read_json(path, lines=True) for path in (tmp_path / "run/steps").glob("*.jsonl")]
    exports = next(f for f in frames if "episode_export" in f)["episode_export"].tolist()
    assert exports[0]["status"] == "exported"
    merged = finalize_dataset(exports, tmp_path / "merged", task_text="Move the fixture object")
    assert merged["accepted_count"] == 1
    assert merged["validation"]["valid"]
    table = pq.read_table(tmp_path / "merged/data/chunk-000/episode_000000.parquet")
    assert table.num_rows == merged["validation"]["frame_count"]
    assert table["episode_index"].to_pylist() == [0] * table.num_rows
    assert EmbodiedDatasetValidator().transform(merged)["status"] == "validated"
    with pytest.raises(ValueError, match="runtime failures"):
        finalize_dataset([*exports, {"status": "runtime_failed"}], tmp_path / "bad", task_text="fixture")
    with pytest.raises(ValueError, match="duplicate"):
        finalize_dataset(exports * 2, tmp_path / "duplicate", task_text="fixture")


def test_export_requires_explicit_review_and_isolates_source(self_collected_path, tmp_path):
    planner = EmbodiedCleaningPlanner(idle_min_duration_s=10)
    planned = planner.transform({"path": str(self_collected_path)})
    exporter = EmbodiedLeRobotExporter(tmp_path / "out")
    with pytest.raises(ValueError, match="task_text"):
        exporter.transform(planned)
    reviewed = planner.transform(episode_spec(self_collected_path))
    with pytest.raises(ValueError, match="outside"):
        EmbodiedLeRobotExporter(self_collected_path / "output").transform(reviewed)
    result = exporter.transform(reviewed)
    assert result["status"] == "exported"
    with pytest.raises(ValueError, match="existing"):
        exporter.transform(reviewed)


def test_runtime_failure_does_not_look_like_quality_rejection(tmp_path):
    from dataflow.utils.storage import FileStorage
    inputs = tmp_path / "missing.jsonl"
    inputs.write_text(json.dumps({"episode": {"path": str(tmp_path / "missing-source")}}) + "\n")
    storage = FileStorage(first_entry_file_name=str(inputs), cache_path=str(tmp_path / "steps"), cache_type="jsonl")
    EmbodiedCleaningPlanner().run(storage=storage.step(), input_key="episode", output_key="result")
    result = pd.read_json(next((tmp_path / "steps").glob("*.jsonl")), lines=True).iloc[0]["result"]
    assert result["status"] == "runtime_failed"
    assert "source not found" in result["error"]["reason"]


def test_lerobot_v21_can_be_cleaned_without_platform(lerobot_v21_online_path, tmp_path):
    planned = EmbodiedCleaningPlanner(idle_min_duration_s=10).transform(episode_spec(lerobot_v21_online_path))
    result = EmbodiedLeRobotExporter(tmp_path / "converted").transform(planned)
    assert result["status"] == "exported"
    assert EmbodiedDatasetValidator().transform(result)["validation"]["valid"]
