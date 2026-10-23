"""Artificial S2 fixture adapted from attributed OpenHands MIT tests."""
import csv
import json
from pathlib import Path
import imageio_ffmpeg
import numpy as np
from .adapters import S2_REFERENCE_JOINT_ORDER

def create_fixture(tmp_path: Path) -> Path:
    episode = tmp_path / 'synthetic-episode'
    episode.mkdir()
    writer = imageio_ffmpeg.write_frames(str(episode / 'head.mp4'), (16, 16), fps=30, codec='mpeg4', pix_fmt_in='rgb24', pix_fmt_out='yuv420p')
    writer.send(None)
    for index in range(21):
        frame = np.full((16, 16, 3), index * 5, dtype=np.uint8)
        writer.send(frame.tobytes())
    writer.close()
    (episode / 'head_depth.u16').write_bytes(b'')
    with (episode / 'head.csv').open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['frame_index', 'wall_time', 'stamp_sec', 'stamp_nsec'])
        writer.writeheader()
        for index in range(21):
            offset_ns = index * 100000000
            writer.writerow({'frame_index': index, 'wall_time': 100.0 + index / 10, 'stamp_sec': 100 + offset_ns // 1000000000, 'stamp_nsec': offset_ns % 1000000000})
    with (episode / 'head_depth.csv').open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['frame_index', 'wall_time', 'stamp_ns'])
        writer.writeheader()
    joint_rows = []
    for index in range(21):
        if index < 8:
            joint_value = 0.0
        elif index <= 12:
            joint_value = (index - 7) * 0.1
        else:
            joint_value = 0.5
        joint_rows.append({'wall_time': 100.0 + index / 10, 'stamp_ns': 100000000000 + index * 100000000, 'joints': {name: joint_value for name in S2_REFERENCE_JOINT_ORDER}, 'left_ee_states': [0.0, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0], 'right_ee_states': [0.0, 0.0, 0.0, 0.0, 0.02, 0.0, 0.0], 'suction_state': 0, 'subtask': 'move' if 8 <= index <= 12 else ''})
    (episode / 'joints.jsonl').write_text(''.join((json.dumps(row) + '\n' for row in joint_rows)), encoding='utf-8')
    (episode / 'manifest.json').write_text(json.dumps({'composition_id': 'demo', 'steps': [{'step_id': 'move_arm', 'type': 'move_arm', 'subtask': 'approach_object', 'started_at': 100.8, 'completed_at': 101.3}, {'step_id': 'enable_suction', 'type': 'suction', 'subtask': 'grasp_object', 'started_at': 101.2, 'completed_at': 101.4}]}) + '\n', encoding='utf-8')
    return episode
