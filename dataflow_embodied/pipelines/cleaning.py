from pathlib import Path

from dataflow.pipeline import PipelineABC, StreamBatchedPipelineABC
from dataflow.utils.storage import FileStorage, StreamBatchedFileStorage

from ..operators.episodes import EmbodiedCleaningPlanner, EmbodiedLeRobotExporter


class EmbodiedCleaningPipeline(PipelineABC):
    """Process one manifest row per episode; merge only after every batch finishes."""
    def __init__(self, input_path, output_dir, **planner_options):
        super().__init__()
        output = Path(output_dir)
        self.storage = FileStorage(first_entry_file_name=str(input_path), cache_path=str(output / "steps"),
                                   file_name_prefix="embodied", cache_type="jsonl")
        self.planner = EmbodiedCleaningPlanner(**planner_options)
        self.exporter = EmbodiedLeRobotExporter(output / "parts")

    def forward(self):
        self.planner.run(storage=self.storage.step(), input_key="episode", output_key="cleaning_plan")
        self.exporter.run(storage=self.storage.step(), input_key="cleaning_plan", output_key="episode_export")


class EmbodiedCleaningStreamPipeline(StreamBatchedPipelineABC):
    """Stream episode manifests; dataset finalization remains a separate full-run step."""
    def __init__(self, input_path, output_dir, **planner_options):
        super().__init__()
        output = Path(output_dir)
        self.storage = StreamBatchedFileStorage(first_entry_file_name=str(input_path), cache_path=str(output / "steps"),
                                                file_name_prefix="embodied", cache_type="jsonl")
        self.planner = EmbodiedCleaningPlanner(**planner_options)
        self.exporter = EmbodiedLeRobotExporter(output / "parts")

    def forward(self):
        self.planner.run(storage=self.storage.step(), input_key="episode", output_key="cleaning_plan")
        self.exporter.run(storage=self.storage.step(), input_key="cleaning_plan", output_key="episode_export")

    def _compiled_forward(self, resume_step=0, batch_size=8, resume_from_last=False):
        if resume_step != 0 or resume_from_last:
            raise ValueError("extension stream pipeline requires a fresh run; resume is unsupported")
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if any(Path(self.storage.cache_path).glob("embodied_step*.jsonl")):
            raise ValueError("output already contains step results; choose a new directory")
        return super()._compiled_forward(resume_step=0, batch_size=batch_size, resume_from_last=False)


def finalize_dataset(exports, output_dir, *, task_text):
    """Dataset-level merge: never invoke this once per batch or silently drop failures."""
    from ..core.lerobot_v21 import merge_lerobot_v21_datasets, validate_lerobot_v21_dataset
    exports = list(exports)
    failed = [x for x in exports if x.get("status") == "runtime_failed"]
    unknown = [x for x in exports if x.get("status") not in {"exported", "quality_rejected", "runtime_failed"}]
    if failed or unknown:
        raise ValueError("unresolved runtime failures or unfinished episodes; finalize refused")
    accepted = [x for x in exports if x.get("status") == "exported"]
    if not accepted:
        raise ValueError("no accepted episodes to merge")
    paths = [Path(x["dataset_path"]).resolve() for x in accepted]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate episode exports")
    output = Path(output_dir).resolve()
    if any(output.is_relative_to(p) for p in paths):
        raise ValueError("merged output must be outside episode datasets")
    merge_lerobot_v21_datasets(paths, output, task_text=task_text)
    report = validate_lerobot_v21_dataset(output)
    if not report.valid:
        raise ValueError(f"merged dataset failed validation: {report.errors}")
    return {"dataset_path": str(output), "validation": report.model_dump(mode="json"),
            "accepted_count": len(accepted),
            "rejected": [x for x in exports if x.get("status") == "quality_rejected"]}
