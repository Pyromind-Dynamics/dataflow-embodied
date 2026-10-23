from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from dataflow_embodied import EmbodiedCleaningPlanner, EmbodiedLeRobotExporter, EmbodiedDatasetValidator
from dataflow_embodied.pipelines.cleaning import EmbodiedCleaningPipeline, EmbodiedCleaningStreamPipeline, finalize_dataset
from dataflow_embodied.core.timestamps import nearest_timestamp_indexes
from test_extension import episode_spec

pytestmark=[pytest.mark.cpu,pytest.mark.media]


@pytest.mark.parametrize('batch_size',[1,2])
def test_multi_episode_stream_matches_ordinary_and_preserves_failure(self_collected_path,tmp_path,batch_size):
    specs=[]
    for i in range(3):
        target=tmp_path/f'episode-{i}'
        shutil.copytree(self_collected_path,target)
        specs.append(episode_spec(target))
    specs.insert(1,episode_spec(tmp_path/'intentionally-missing'))
    manifest=tmp_path/'input.jsonl'
    manifest.write_text(''.join(json.dumps({'episode':x})+'\n' for x in specs))
    datasets=[]
    plans=[]
    for name,kind in [('ordinary',EmbodiedCleaningPipeline),('stream',EmbodiedCleaningStreamPipeline)]:
        output=tmp_path/name
        pipeline=kind(manifest,output,idle_min_duration_s=10)
        pipeline.compile()
        if name=='stream':pipeline.forward(batch_size=batch_size)
        else:pipeline.forward()
        rows=[json.loads(x) for x in (output/'steps/embodied_step2.jsonl').read_text().splitlines()]
        exports=[x['episode_export'] for x in rows]
        assert [x['status'] for x in exports]==['exported','runtime_failed','exported','exported']
        plans.append([x['cleaning_plan'] for x in rows])
        with pytest.raises(ValueError,match='runtime failures'):
            finalize_dataset(exports,tmp_path/f'{name}-refused',task_text='fixture')
        final=finalize_dataset([x for x in exports if x['status']=='exported'],tmp_path/f'{name}-final',task_text='fixture')
        assert final['accepted_count']==3 and final['validation']['frame_count']==63
        table=pq.read_table(Path(final['dataset_path'])/'data')
        assert table['index'].to_pylist()==list(range(63))
        assert table['episode_index'].to_pylist()==[0]*21+[1]*21+[2]*21
        datasets.append(table)
    assert plans[0]==plans[1]
    assert datasets[0].equals(datasets[1])


def test_encoder_failure_leaves_no_partial_dataset_and_can_retry(self_collected_path,tmp_path,monkeypatch):
    from dataflow_embodied.core import lerobot_v21
    before={str(p):p.read_bytes() for p in self_collected_path.rglob('*') if p.is_file()}
    planned=EmbodiedCleaningPlanner(idle_min_duration_s=10).transform(episode_spec(self_collected_path))
    exporter=EmbodiedLeRobotExporter(tmp_path/'output')
    with monkeypatch.context() as patch:
        def fail(*args,**kwargs):raise RuntimeError('injected video encoding failure')
        patch.setattr(lerobot_v21,'_write_videos',fail)
        with pytest.raises(RuntimeError,match='injected'):
            exporter.transform(planned)
    assert not list((tmp_path/'output/episodes').iterdir())
    assert {str(p):p.read_bytes() for p in self_collected_path.rglob('*') if p.is_file()}==before
    result=exporter.transform(planned)
    assert result['status']=='exported'
    assert EmbodiedDatasetValidator().transform(result)['status']=='validated'


def test_corrupted_export_indexes_are_rejected(self_collected_path,tmp_path):
    planned=EmbodiedCleaningPlanner(idle_min_duration_s=10).transform(episode_spec(self_collected_path))
    result=EmbodiedLeRobotExporter(tmp_path/'out').transform(planned)
    file=Path(result['dataset_path'])/'data/chunk-000/episode_000000.parquet'
    table=pq.read_table(file)
    position=table.schema.get_field_index('index')
    table=table.set_column(position,'index',pa.array([0]*table.num_rows,type=pa.int64()))
    pq.write_table(table,file)
    rejected=EmbodiedDatasetValidator().transform(result)
    assert rejected['status']=='quality_rejected' and not rejected['validation']['valid']


@pytest.mark.parametrize('seed',range(5))
def test_alignment_matches_independent_nearest_neighbor_oracle(seed):
    rng=np.random.default_rng(seed)
    for _ in range(20):
        targets=sorted(rng.choice(1_000_000,size=64,replace=False).tolist())
        references=sorted(rng.choice(1_000_000,size=80,replace=False).tolist())
        target_rows=[{'stamp_ns':100_000_000_000+x*1000} for x in targets]
        reference_rows=[{'stamp_ns':100_000_000_000+x*1000} for x in references]
        target_times=[x['stamp_ns']/1e9 for x in target_rows]
        expected=[min(range(len(targets)),key=lambda i:abs(target_times[i]-row['stamp_ns']/1e9)) for row in reference_rows]
        actual=nearest_timestamp_indexes(reference_rows,target_rows,list(range(80)),max_gap_s=2)
        assert actual==expected
