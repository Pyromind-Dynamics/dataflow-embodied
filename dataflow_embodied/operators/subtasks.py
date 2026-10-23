"""DataFlow operator for standalone subtasks.json conversion."""
import hashlib
import json
from pathlib import Path

from dataflow.utils.registry import OPERATOR_REGISTRY
from ._contracts import describe
from .episodes import _EmbodiedMapper, _source


@OPERATOR_REGISTRY.register()
class EmbodiedSubtaskExporter(_EmbodiedMapper):
    @staticmethod
    def get_desc(lang: str = "zh") -> str:
        return describe(EmbodiedSubtaskExporter, lang)

    def __init__(self, output_dir: str, *, on_error='isolate'):
        super().__init__(on_error=on_error)
        self.output_dir = Path(output_dir).resolve()

    def transform(self, spec):
        from ..core.subtasks import export_source_subtasks
        source = _source(spec)
        if self.output_dir.is_relative_to(source):
            raise ValueError('Subtask output must be outside the input source')
        payload = export_source_subtasks(source, episode_id=spec.get('episode_id'),
                                         task_text=spec.get('task_text'))
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
        identity = json.dumps([str(source), payload['provenance']['episode_id']])
        token = hashlib.sha256(identity.encode()).hexdigest()[:20]
        destination = self.output_dir / token / 'subtasks.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation preserves an earlier export and any user edits.
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
        return {'status': 'subtasks_exported', 'subtasks_path': str(destination),
                'segment_count': len(payload['segments']), 'review_required': True,
                'mode': 'source_labels', 'model_called': False}

