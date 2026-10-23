"""Public field contracts against real DataFlow compilation and storage boundaries."""
import inspect
import json

import pandas as pd
import pytest
from dataflow.pipeline import PipelineABC
from dataflow.utils.storage import FileStorage
import dataflow_embodied as extension

pytestmark = pytest.mark.cpu
NAMES = ['EmbodiedDatasetInspector', 'EmbodiedCleaningPlanner', 'EmbodiedLeRobotExporter', 'EmbodiedDatasetValidator', 'EmbodiedSubtaskExporter']


class NeverServing:
    def generate_from_input_multi_images(self, **kwargs):
        raise AssertionError('compilation/field rejection must not call a model')


def make_operator(name, tmp_path):
    serving = NeverServing()
    options = {
        'EmbodiedLeRobotExporter': dict(output_dir=tmp_path / 'products'),
        'EmbodiedSubtaskExporter': dict(output_dir=tmp_path / 'products'),
    }
    return getattr(extension, name)(**options.get(name, {}))


class ContractPipeline(PipelineABC):
    def __init__(self, op, source, cache, use_defaults):
        super().__init__()
        self.op = op
        self.storage = FileStorage(str(source), cache_path=str(cache), cache_type='jsonl')
        self.use_defaults = use_defaults

    def forward(self):
        if self.use_defaults:
            self.op.run(storage=self.storage.step())
        else:
            self.op.run(storage=self.storage.step(), input_key='custom_input', output_key='custom_output')


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('mode', ['default', 'custom', 'missing'])
def test_compile_declares_real_dependencies_without_execution(name, mode, tmp_path):
    op = make_operator(name, tmp_path)
    signature = inspect.signature(op.run)
    input_key = signature.parameters['input_key'].default if mode == 'default' else 'custom_input'
    output_key = signature.parameters['output_key'].default if mode == 'default' else 'custom_output'
    source = tmp_path / 'input.jsonl'
    source.write_text(json.dumps({'unrelated' if mode == 'missing' else input_key: {'path': '/missing'}})+'\n')
    before = {str(p) for p in tmp_path.rglob('*') if p.is_file()}
    pipeline = ContractPipeline(op, source, tmp_path / 'steps', mode == 'default')
    if mode == 'missing':
        with pytest.raises(KeyError):
            pipeline.compile()
    else:
        pipeline.compile()
        node = next(node for node in pipeline.op_nodes_list if node.op_obj is op)
        assert set(node.input_keys) == {input_key}
        assert set(node.output_keys) == {output_key}
    assert {str(p) for p in tmp_path.rglob('*') if p.is_file()} == before


class MemoryStorage:
    def __init__(self, frame):
        self.frame = frame.copy(deep=True)
        self.writes = 0
    def read(self, kind): return self.frame
    def write(self, frame):
        self.frame = frame
        self.writes += 1


@pytest.mark.parametrize('name', NAMES)
def test_existing_output_rejected_before_side_effects(name, tmp_path):
    op = make_operator(name, tmp_path)
    original = pd.DataFrame({'source': [{'path': '/missing'}], 'kept': ['keep me']})
    storage = MemoryStorage(original)
    with pytest.raises(ValueError, match='already exists'):
        op.run(storage, input_key='source', output_key='kept')
    pd.testing.assert_frame_equal(storage.frame, original)
    assert storage.writes == 0
    assert not (tmp_path / 'products').exists()


@pytest.mark.parametrize('name', NAMES)
def test_empty_input_keeps_schema_and_missing_column_is_task_error(name, tmp_path):
    op = make_operator(name, tmp_path)
    storage = MemoryStorage(pd.DataFrame(columns=['source', 'unrelated']))
    assert op.run(storage, input_key='source', output_key='result') == 'result'
    assert list(storage.frame.columns) == ['source', 'unrelated', 'result']
    assert len(storage.frame) == 0
    with pytest.raises(KeyError, match='missing input column'):
        op.run(MemoryStorage(pd.DataFrame({'other': [1]})), input_key='source', output_key='result')
    assert not (tmp_path / 'products').exists()


@pytest.mark.parametrize('name', NAMES)
def test_real_episode_processing_retains_success_and_failed_positions(name, self_collected_path, tmp_path):
    spec = {'path': str(self_collected_path), 'task_text': 'Fixture task',
            'confirm_subtasks': True, 'confirm_derived_action': True}
    op = make_operator(name, tmp_path)
    good, bad = spec, {'path': str(tmp_path / 'missing')}
    if name == 'EmbodiedLeRobotExporter':
        good = extension.EmbodiedCleaningPlanner(idle_min_duration_s=10).transform(spec)
        bad = {'status': 'runtime_failed', 'error': {'reason': 'upstream failure'}}
    elif name == 'EmbodiedDatasetValidator':
        planned = extension.EmbodiedCleaningPlanner(idle_min_duration_s=10).transform(spec)
        good = extension.EmbodiedLeRobotExporter(tmp_path / 'valid-dataset').transform(planned)
    original = pd.DataFrame({'source': [bad, good], 'id': ['bad-first', 'good-second']})
    storage = MemoryStorage(original)
    op.run(storage, input_key='source', output_key='result')
    pd.testing.assert_frame_equal(storage.frame[['source', 'id']], original)
    assert storage.frame['result'].iloc[0]['status'] == ('quality_rejected' if name == 'EmbodiedDatasetValidator' else 'runtime_failed')
    assert storage.frame['result'].iloc[1]['status'] in {'inspected', 'planned', 'exported', 'validated', 'subtasks_exported'}
