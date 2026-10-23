"""Convert source task intervals to a standalone subtasks document."""
from __future__ import annotations

import math
from pathlib import Path

from .adapters import build_episode_plan


def export_source_subtasks(source: Path, *, episode_id=None, task_text=None):
    """Preserve existing labels, rather than claiming visual task recognition."""
    plan = build_episode_plan(source, episode_id=episode_id)
    if not plan.segments:
        raise ValueError('No source subtask labels; visual task recognition requires a model')
    if task_text is not None and (not isinstance(task_text, str) or not task_text.strip()):
        raise ValueError('task_text must be nonblank text')
    summary = task_text if task_text is not None else plan.task.text
    base = plan.source_timeline.start_stamp_ns
    fps = plan.source_timeline.fps
    segments = []
    for index, segment in enumerate(plan.segments):
        if base is not None and segment.source_start_ns is not None and segment.source_end_ns is not None:
            start = (segment.source_start_ns - base) / 1e9
            end = (segment.source_end_ns - base) / 1e9
            basis = 'sensor_timestamp'
        elif base is None and fps is not None:
            start = segment.source_start_frame / fps
            end = segment.source_end_frame / fps
            basis = 'frame_index/fps'
        else:
            raise ValueError('Source labels have no convertible timestamp or frame rate')
        if not all(math.isfinite(x) for x in (start, end)) or start < 0 or end <= start:
            raise ValueError('Invalid source subtask time interval')
        segments.append({
            'proposal_id': f'ACTION_{index:02d}', 'event_type': segment.event_type,
            'label': segment.instruction, 'instruction': segment.instruction,
            'start_s': start, 'end_s': end,
            'state_before': 'unknown', 'state_after': 'unknown',
            'evidence': {'origin': segment.origin}, 'telemetry_support': [],
            'confidence': segment.confidence,
            'uncertainty': 'Source label conversion only; no visual recognition or human review',
            'source_timeline': {
                'start_frame': segment.source_start_frame,
                'end_frame': segment.source_end_frame,
                'end_frame_exclusive': True,
                'start_stamp_ns': segment.source_start_ns,
                'end_stamp_ns': segment.source_end_ns,
                'time_basis': basis,
            },
        })
    return {
        'task_summary': summary, 'segments': segments,
        'provenance': {'mode': 'source_labels', 'episode_id': plan.episode_id,
                       'model_called': False, 'review_required': True,
                       'warnings': list(plan.quality.warnings)},
    }
