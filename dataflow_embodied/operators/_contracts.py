"""Field safety and operator descriptions; no model or media I/O at import time."""
import inspect


def read_new_output(storage, input_key: str, output_key: str):
    """Reject field mistakes before model calls or external artifact writes."""
    if not isinstance(input_key, str) or not input_key.strip():
        raise ValueError("input_key must be a non-empty string")
    if not isinstance(output_key, str) or not output_key.strip():
        raise ValueError("output_key must be a non-empty string")
    if input_key == output_key:
        raise ValueError("output_key must preserve the source input column")
    frame = storage.read("dataframe")
    if input_key not in frame.columns:
        raise KeyError(f"missing input column: {input_key}")
    if output_key in frame.columns:
        raise ValueError(f"output column already exists: {output_key}; choose a new output_key")
    return frame


def describe(cls, lang="zh"):
    """Use real signatures for defaults and per-operator semantic descriptions."""
    index = 0 if lang == "zh" else 1
    spec = _SPECS[cls.__name__]
    lines = [cls.__name__ + ": " + spec["purpose"][index]]
    lines.append("初始化参数：" if index == 0 else "Constructor parameters:")
    for name, parameter in inspect.signature(cls).parameters.items():
        default = ("必填" if index == 0 else "required") if parameter.default is inspect.Parameter.empty else repr(parameter.default)
        lines.append(f"- {name} ({default}): {_PARAMS[name][index]}")
    lines.append("字段参数：" if index == 0 else "Field parameters:")
    for name, parameter in inspect.signature(cls.run).parameters.items():
        if name in {"self", "storage"}:
            continue
        detail = spec["input"][index] if name.startswith("input_") else spec["output"][index]
        lines.append(f"- {name} ({parameter.default!r}): {detail}")
    lines.append(("run 通过 storage 读写 DataFrame，新增结果列，保留行数、顺序和所有源列；输出列必须尚不存在。返回 output_key 字符串。" if index == 0 else
                  "run reads/writes a DataFrame through storage, adding a new result column while preserving row count, order and all source columns. The output column must not exist. Returns the output_key string."))
    lines.append(spec["effects"][index])
    if cls.__name__.startswith("Embodied"):
        lines.append("直接 transform(value) 不经过逐行隔离，错误直接抛出。run 的 on_error 仅处理预期记录级错误；Storage/字段错误抛出。" if index == 0 else
                     "Direct transform(value) bypasses row isolation and propagates errors. run on_error handles expected record errors only; Storage/field errors propagate.")
    return "\n".join(lines)


_PARAMS = {'on_error': ('isolate 保留失败行；raise 抛出预期记录错误。整列缺失、输出冲突及 Storage 错误始终抛出。',
              'isolate retains failed rows; raise propagates expected record errors. Missing '
              'columns, output conflicts and Storage errors always propagate.'),
 'output_dir': ('本地输出目录，须在来源之外；已有产物不覆盖。',
                'Local output directory outside the source; existing artifacts are not '
                'overwritten.'),
 'motion_speed_threshold': ('静止判定的速度阈值，有限正数；单位沿用来源特征约定。',
                            'Finite positive speed threshold for idle detection, using source '
                            'feature units.'),
 'idle_min_duration_s': ('判定静止片段的最短时长（秒），有限正数。',
                         'Finite positive minimum idle duration in seconds.'),
 'context_s': ('分段边界保留的上下文秒数，有限非负数。',
               'Finite nonnegative context duration around segment boundaries in seconds.'),
 'robot_type': ('导出元信息中的机器人类型；本版只验证 S2 参考特征。',
                'Robot type in exported metadata; only the S2 reference features are validated in '
                'this version.')}

_SPECS = {'EmbodiedDatasetInspector': {'purpose': ('检查已有具身来源、episode 和媒体/状态载荷。',
                                          'Inspect embodied sources, episodes and media/state '
                                          'payloads.'),
                              'input': ('episode 字典：path，按来源需要可带 episode_id。',
                                        'episode dict: path and episode_id when required by the '
                                        'source.'),
                              'output': ('status=inspected、source_path、inspection；失败为 '
                                         'runtime_failed。',
                                         'status=inspected, source_path and inspection; '
                                         'runtime_failed on execution errors.'),
                              'effects': ('只读来源，不调用模型、不导出视频；检查成功不等于能够物化。',
                                          'Read-only inspection, without model calls or video '
                                          'export; successful inspection does not imply '
                                          'materializability.')},
 'EmbodiedCleaningPlanner': {'purpose': ('为每条 episode 生成对齐与静止片段清理计划。',
                                         'Plan alignment and idle-segment cleaning for each '
                                         'episode.'),
                             'input': ('episode 字典：path，可选 '
                                       'episode_id/task_text/confirm_subtasks/confirm_derived_action。',
                                       'episode dict: path, optional '
                                       'episode_id/task_text/confirm_subtasks/confirm_derived_action.'),
                             'output': ('status=planned/quality_rejected、source_path、plan、options、config；故障 '
                                        'runtime_failed。',
                                        'status=planned/quality_rejected, source_path, plan, '
                                        'options and config; runtime_failed on errors.'),
                             'effects': ('读取来源生成计划，不物化清理文件、不调用模型；计划内帧区间变化不改变外层行数。',
                                         'Reads sources to plan without materializing files or '
                                         'calling models; frame-interval changes do not change '
                                         'outer row counts.')},
 'EmbodiedLeRobotExporter': {'purpose': ('执行已确认的清理计划并导出单 episode LeRobot v2.1。',
                                         'Materialize a confirmed cleaning plan as one LeRobot '
                                         'v2.1 episode.'),
                             'input': ('规划结果：status/source_path/plan/options；options 需显式 task_text '
                                       '及相关布尔确认。',
                                       'Planning result with status/source_path/plan/options; '
                                       'options require explicit task_text and relevant boolean '
                                       'confirmations.'),
                             'output': ('status=exported、dataset_path、materialization、plan；质量拒绝/失败保留对应状态。',
                                        'status=exported, dataset_path, materialization and plan; '
                                        'quality rejections/failures retain their states.'),
                             'effects': ('写视频、Parquet 和元信息，不调用模型；拒绝已有输出。传入的 '
                                         'quality_rejected/runtime_failed 原样传递；全数据集合并另行 '
                                         'finalize_dataset。',
                                         'Writes videos, Parquet and metadata, without models; '
                                         'refuses existing outputs. Input '
                                         'quality_rejected/runtime_failed results pass through; '
                                         'finalize_dataset separately merges the full run.')},
 'EmbodiedDatasetValidator': {'purpose': ('为每条数据集引用新增 LeRobot v2.1 验证报告。',
                                          'Add a LeRobot v2.1 validation report to each dataset '
                                          'reference.'),
                              'input': ('含 dataset_path 或 path 的字典。',
                                        'Dict containing dataset_path or path.'),
                              'output': ('原字典追加 status=validated/quality_rejected 和 '
                                         'validation；运行故障 runtime_failed。',
                                         'Original dict plus status=validated/quality_rejected and '
                                         'validation; runtime_failed on execution errors.'),
                              'effects': ('读取文件，不改写数据集、不调用模型。缺失或损坏载荷可在报告中判为 '
                                          'quality_rejected；读取过程异常才是 runtime_failed。每条数据集引用仍保留一行。',
                                          'Reads files without modifying datasets or calling '
                                          'models. Missing/damaged payloads may be reported as '
                                          'quality_rejected; execution exceptions become '
                                          'runtime_failed. Each dataset reference remains one '
                                          'row.')},
 'EmbodiedSubtaskExporter': {'purpose': ('将来源中已有步骤标签和时间区间转换为 subtasks.json。',
                                         'Convert existing source step labels and intervals to '
                                         'subtasks.json.'),
                             'input': ('episode 字典：path，可选 episode_id/task_text；来源必须已有标签和可靠时间。',
                                       'episode dict: path, optional episode_id/task_text; source '
                                       'must have labels and reliable timing.'),
                             'output': ('status=subtasks_exported、subtasks_path、segment_count、review_required=true、model_called=false；故障 '
                                        'runtime_failed。',
                                        'status=subtasks_exported, subtasks_path, segment_count, '
                                        'review_required=true and model_called=false; '
                                        'runtime_failed on errors.'),
                             'effects': ('写 '
                                         'output_dir/<来源标识>/subtasks.json；不覆盖已有文件，不理解视频或补造描述。无标签/可靠时间时失败，结果仍需复核。',
                                         'Writes output_dir/<source identity>/subtasks.json; never '
                                         'overwrites files, interprets video or invents '
                                         'descriptions. Missing labels/reliable timing fail; '
                                         'results still require review.')}}
