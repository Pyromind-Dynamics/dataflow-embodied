"""DataFlow adapters over isolated deterministic episode processing functions."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from ._contracts import describe, read_new_output


def _source(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
        raise ValueError("episode spec requires a path string")
    path = Path(spec["path"]).resolve()
    if not path.exists():
        raise ValueError(f"source not found: {path}")
    return path


class _EmbodiedMapper(OperatorABC):
    def __init__(self, *, on_error="isolate"):
        super().__init__()
        if on_error not in {"raise", "isolate"}:
            raise ValueError("on_error must be raise or isolate")
        self.on_error = on_error

    def run(self, storage, input_key: str = "episode", output_key: str = "embodied_result"):
        frame = read_new_output(storage, input_key, output_key)
        results = []
        for spec in frame[input_key]:
            try:
                results.append(self.transform(spec))
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
                if self.on_error == "raise":
                    raise
                results.append({"status": "runtime_failed", "error": {
                    "stage": self.__class__.__name__, "type": type(exc).__name__, "reason": str(exc)},
                    "source": spec})
        frame[output_key] = results
        storage.write(frame)
        return output_key


@OPERATOR_REGISTRY.register()
class EmbodiedDatasetInspector(_EmbodiedMapper):
    @staticmethod
    def get_desc(lang: str = "zh") -> str:
        return describe(EmbodiedDatasetInspector, lang)

    def transform(self, spec):
        from ..core.adapters import inspect_dataset
        path = _source(spec)
        return {"status": "inspected", "source_path": str(path),
                "inspection": inspect_dataset(path).model_dump(mode="json")}


@OPERATOR_REGISTRY.register()
class EmbodiedCleaningPlanner(_EmbodiedMapper):
    @staticmethod
    def get_desc(lang: str = "zh") -> str:
        return describe(EmbodiedCleaningPlanner, lang)

    def __init__(self, *, motion_speed_threshold=0.02, idle_min_duration_s=1.5,
                 context_s=0.5, on_error="isolate"):
        super().__init__(on_error=on_error)
        for key, value in [("motion_speed_threshold", motion_speed_threshold),
                           ("idle_min_duration_s", idle_min_duration_s), ("context_s", context_s)]:
            if not math.isfinite(value) or value < 0 or (key != "context_s" and value == 0):
                raise ValueError(f"invalid {key}")
        self.config = dict(motion_speed_threshold=motion_speed_threshold,
                           idle_min_duration_s=idle_min_duration_s, context_s=context_s)

    def transform(self, spec):
        from ..core.planning import plan_episode_cleaning
        path = _source(spec)
        plan = plan_episode_cleaning(path, episode_id=spec.get("episode_id"), **self.config)
        return {"status": "quality_rejected" if plan.quality.status == "rejected" else "planned",
                "source_path": str(path), "plan": plan.model_dump(mode="json"),
                "options": {key: spec.get(key) for key in ("task_text", "confirm_subtasks", "confirm_derived_action")},
                "config": self.config}


@OPERATOR_REGISTRY.register()
class EmbodiedLeRobotExporter(_EmbodiedMapper):
    @staticmethod
    def get_desc(lang: str = "zh") -> str:
        return describe(EmbodiedLeRobotExporter, lang)

    def __init__(self, output_dir, *, robot_type="s2", on_error="isolate"):
        super().__init__(on_error=on_error)
        self.output_dir = Path(output_dir).resolve()
        self.robot_type = robot_type

    def transform(self, planned):
        from ..core.models import EpisodePlan
        from ..core.planning import finalize_episode_plan
        from ..core.lerobot_v21 import materialize_finalized_lerobot_v21_episode
        if planned.get("status") in {"quality_rejected", "runtime_failed"}:
            return planned
        if planned.get("status") != "planned":
            raise ValueError("export requires a cleaning plan")
        source = Path(planned["source_path"]).resolve()
        if self.output_dir.is_relative_to(source):
            raise ValueError("export output must be outside the input source")
        candidate = EpisodePlan.model_validate(planned["plan"])
        options = planned["options"]
        for key in ("confirm_subtasks", "confirm_derived_action"):
            if options.get(key) is not None and type(options[key]) is not bool:
                raise ValueError(f"{key} must be an explicit boolean")
        if not isinstance(options.get("task_text"), str) or not options["task_text"].strip():
            raise ValueError("task_text must be supplied explicitly")
        finalized = finalize_episode_plan(source, candidate, task_text=options["task_text"],
                     confirm_subtasks=options.get("confirm_subtasks") is True,
                     confirm_derived_action=options.get("confirm_derived_action") is True)
        if finalized.quality.status != "accepted":
            return {**planned, "status": "quality_rejected", "plan": finalized.model_dump(mode="json")}
        token = hashlib.sha256(json.dumps(planned, sort_keys=True).encode()).hexdigest()[:20]
        output = self.output_dir / "episodes" / token
        result = materialize_finalized_lerobot_v21_episode(source, finalized, output, robot_type=self.robot_type)
        return {"status": "exported", "source_path": str(source), "plan": finalized.model_dump(mode="json"),
                "dataset_path": str(output), "materialization": result.model_dump(mode="json")}


@OPERATOR_REGISTRY.register()
class EmbodiedDatasetValidator(_EmbodiedMapper):
    @staticmethod
    def get_desc(lang: str = "zh") -> str:
        return describe(EmbodiedDatasetValidator, lang)

    def transform(self, spec):
        from ..core.lerobot_v21 import validate_lerobot_v21_dataset
        path = spec.get("dataset_path") or spec.get("path")
        if not isinstance(path, str):
            raise ValueError("validation requires a dataset_path")
        report = validate_lerobot_v21_dataset(Path(path))
        return {**spec, "status": "validated" if report.valid else "quality_rejected",
                "validation": report.model_dump(mode="json")}
