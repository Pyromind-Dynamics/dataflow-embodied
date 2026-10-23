import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow.utils.storage import FileStorage
from dataflow_embodied import EmbodiedSubtaskExporter
from dataflow_embodied.core.subtasks import export_source_subtasks

pytestmark = pytest.mark.cpu


def test_source_conversion_preserves_intervals_and_does_not_claim_recognition(self_collected_path, tmp_path):
    before = {str(p): p.read_bytes() for p in self_collected_path.rglob('*') if p.is_file()}
    exporter = EmbodiedSubtaskExporter(str(tmp_path / 'export'))
    result = exporter.transform({'path': str(self_collected_path), 'task_text': 'Provided task'})
    body = json.loads(Path(result['subtasks_path']).read_text())
    assert result['segment_count'] == len(body['segments']) > 0
    assert body['task_summary'] == 'Provided task'
    assert body['provenance']['model_called'] is False
    assert body['provenance']['review_required'] is True
    with (self_collected_path / 'head.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    first = int(rows[0]['stamp_sec']) * 1_000_000_000 + int(rows[0]['stamp_nsec'])
    source_labels = {json.loads(x)['subtask'] for x in (self_collected_path / 'joints.jsonl').read_text().splitlines()}
    for segment in body['segments']:
        assert segment['instruction'] in source_labels
        assert segment['source_timeline']['time_basis'] == 'sensor_timestamp'
        assert segment['start_s'] == pytest.approx((segment['source_timeline']['start_stamp_ns'] - first) / 1e9)
        assert segment['end_s'] > segment['start_s']
        assert segment['state_before'] == segment['state_after'] == 'unknown'
    assert before == {str(p): p.read_bytes() for p in self_collected_path.rglob('*') if p.is_file()}


def test_export_does_not_overwrite_previous_output_or_source(self_collected_path, tmp_path):
    exporter = EmbodiedSubtaskExporter(str(tmp_path / 'export'))
    result = exporter.transform({'path': str(self_collected_path)})
    path = Path(result['subtasks_path'])
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        exporter.transform({'path': str(self_collected_path)})
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match='outside'):
        EmbodiedSubtaskExporter(str(self_collected_path / 'output')).transform({'path': str(self_collected_path)})


def test_no_labels_refuses_to_invent_semantic_tasks(self_collected_path):
    joints = self_collected_path / 'joints.jsonl'
    rows = [json.loads(x) for x in joints.read_text().splitlines()]
    for row in rows:
        row['subtask'] = ''
    joints.write_text(''.join(json.dumps(x) + '\n' for x in rows))
    manifest = self_collected_path / 'manifest.json'
    body = json.loads(manifest.read_text()); body['steps'] = []
    manifest.write_text(json.dumps(body))
    with pytest.raises(ValueError, match='requires a model'):
        export_source_subtasks(self_collected_path)


def test_registry_and_storage_conversion(self_collected_path, tmp_path):
    assert OPERATOR_REGISTRY.get('EmbodiedSubtaskExporter') is EmbodiedSubtaskExporter
    source = tmp_path / 'input.jsonl'
    source.write_text(json.dumps({'id': 'kept', 'episode': {'path': str(self_collected_path)}}) + '\n')
    storage = FileStorage(str(source), cache_path=str(tmp_path / 'cache')).step()
    EmbodiedSubtaskExporter(str(tmp_path / 'export')).run(storage, input_key='episode', output_key='subtasks')
    result = pd.read_json(storage._get_cache_file_path(1), lines=True).iloc[0]
    assert result['id'] == 'kept'
    assert result['subtasks']['status'] == 'subtasks_exported'


def test_invalid_source_is_retained_as_a_failure(tmp_path):
    source = tmp_path / 'input.jsonl'
    source.write_text(json.dumps({'episode': {'path': str(tmp_path / 'missing')}}) + '\n')
    storage = FileStorage(str(source), cache_path=str(tmp_path / 'cache')).step()
    EmbodiedSubtaskExporter(str(tmp_path / 'export')).run(storage, output_key='subtasks')
    result = pd.read_json(storage._get_cache_file_path(1), lines=True).iloc[0]['subtasks']
    assert result['status'] == 'runtime_failed'
    assert 'source not found' in result['error']['reason']
