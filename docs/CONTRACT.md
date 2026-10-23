# 具身 v0.1 契约与接口

## 0.1.2：已有子任务标签转换

`EmbodiedSubtaskExporter(output_dir, on_error='isolate')` 使用相同的 episode 输入列和 Storage 方式，也可直接调用 `transform(spec)`。它将现有 `joints.subtask`、manifest 步骤或已支持来源的标签区间导出为 `output_dir/<来源标识>/subtasks.json`；不执行模型识别。

输出包含 `task_summary`、`segments` 以及来源信息。每段包含 ID、原始标签/说明、`start_s`、`end_s` 和原始帧/时间戳；`end_frame` 为右开边界。存在传感器时间戳时按传感器时钟换算；仅有帧索引和明确 FPS 时才用帧/FPS，不把两种时间基准混用。没有可靠时间基准或已有标签时拒绝转换。

未知的持物状态保留为 unknown，不编造自由/吸附状态、视觉证据或模型置信度。原始标签不自动变成自然语言说明；导出保留待复核标记。数据帧输出为 `status=subtasks_exported`、文件位置和段数；运行故障仍隔离为 `runtime_failed`。输出必须位于输入来源以外，已有文件不覆盖。

本功能满足“将已有采集标签转换为 subtasks 文件”，不等于“仅从视频和无标签关节数据理解并生成新的语义子任务”。后者需要单独的模型算子与输入输出约定。

## 输入

默认 JSONL 每行的 episode 为：

```json
{"path":"/local/source","episode_id":"optional-id","task_text":"自然语言任务","confirm_subtasks":true,"confirm_derived_action":true}
```

path 指向存在的本地 episode/数据集。支持原运行时核实过的 S2 载荷和符合其 S2 特征约定、单任务 LeRobot v2.1；不承诺任意机器人、任意多任务 v2.1 或 v3。仅有标签而没有状态/视频载荷不能物化。

## 算子

所有算子有 `on_error='isolate'`，strict 行为使用 `on_error='raise'`。默认 run 的输入列 episode、输出列 embodied_result；Pipeline 显式使用 cleaning_plan/episode_export。保留源列，不允许输入输出列同名。

- `EmbodiedDatasetInspector`：输出 source_path 和 DatasetInspection，报告来源、episode 和流。
- `EmbodiedCleaningPlanner(motion_speed_threshold=0.02, idle_min_duration_s=1.5, context_s=0.5)`：输出 planned/quality_rejected、完整 EpisodePlan、选项和参数。时钟来源、时间单位、原始到输出帧映射、删除区间均保留。
- `EmbodiedLeRobotExporter(output_dir, robot_type='s2')`：输入清理计划，重新核对源数据并应用显式确认，输出 exported、dataset_path、materialization 和最终 plan。原基线 reference profile 只验证 S2。
- `EmbodiedDatasetValidator`：输入 path/dataset_path，输出 validated/quality_rejected 和校验报告。校验覆盖视频/状态/动作行数、帧、索引、元数据和参考特征等。

映射算子的直接调用入口为 transform(value)。run 中的读取/写入错误仍抛错，逐记录的预期执行错误隔离为 runtime_failed，附源引用、stage/type/reason。质量拒绝则保留 plan.quality，不混同运行故障。

导出前 task_text 必须明确填写；confirm_subtasks 与 confirm_derived_action 只能是布尔值，默认不确认。当源有子任务或推导动作时，必须相应确认；未满足条件时按底层领域校验报错或拒绝，而不会默认批准。

## Pipeline 与最终合并

`EmbodiedCleaningPipeline(input_path, output_dir, **planner_options)` 使用真实 FileStorage 与 PipelineABC：规划 → 单 episode 导出。调用 compile() 后 forward()。输出为分步 JSONL 与外部视频/Parquet，DataFrame 只存引用和报告。

全部批次结束后调用 `finalize_dataset(exports, output_dir, task_text=...)`。有 runtime_failed、未完成状态、重复导出或没有可接受 episode 时拒绝合并；quality_rejected 独立报告，其余可用结果可合并。数据集最终连续重编号并再次校验，不能在每个 batch 内当作全量合并执行。首版以一个明确的任务文本合并，不支持多任务分发。

源数据不原地修改；输出不得在输入源内部，非空输出不覆盖。重复执行导出会明确拒绝已有结果，不宣称自动恢复、幂等文件事务、平台检查点或失败补跑。

## 清理门限与系统依赖

静止判定使用关节/特征速度、持续时长和分段边界上下文。源运行时的对齐规则包括超过 100 ms 的相关告警及超过 500 ms 的质量拒绝；有独立测试覆盖边界、相机首尾偏移和内部状态缺口。具体适用条件由核心 planning 校验决定，不能把单个数字理解为所有具身任务的通用验收标准。当前适配层未暴露任意对齐门限覆盖。

媒体处理依赖 imageio-ffmpeg，Parquet 使用 pyarrow==20.0.0。包导入仅注册适配器，媒体核心在执行时加载。无 Sandbox 镜像、平台凭证或模型调用依赖。首版本地测试不能代替真实数据兼容性、性能和目标平台验收。

## 0.1.1 流式 episode 清单

pipelines.cleaning.EmbodiedCleaningStreamPipeline 与普通 Pipeline 构造参数一致；compile() 后调用 forward(batch_size=8)。每个批次分别完成规划和单 episode 导出，全部批次结束后仍须只调用一次 finalize_dataset。该接口只支持新输出目录，拒绝已有步骤结果，不启用自动恢复。

进一步的本地验证包括多个 episode 在普通和流式执行下的清理计划/最终 Parquet 等价、运行故障不被静默合并、视频编码故障后不留半成品且可重新执行、导出索引损坏可检出，以及 100 组随机时钟的独立最近邻基准核对。这些验证仍不能替代目标业务数据的质量和性能验收。

## 2026-10-23 字段契约与调用边界

所有公开 `run(storage, input_key=..., output_key=...)` 均要求非空字符串字段名，输入列必须存在，输出列必须尚不存在。整列缺失、同名输出和 Storage 读写错误属于任务错误，即使 `on_error="isolate"` 也不隔离。输出冲突在模型调用和外部文件写入之前拒绝；迁移已有覆盖用法时选择新输出列。

算子新增结果列，保留外层 DataFrame 的条数、顺序和所有输入列；内部框、子任务段或视频帧的数量变化不等于表格删行。每条结果的领域质量与运行状态分别解释。直接 `transform` / `synthesize` 不经过 Storage 的逐记录隔离层，错误直接抛出；模型算子的 `process` 则遵循其 on_error 配置。

每个公开类的 `get_desc("zh"/"en")` 可独立读取功能、构造参数、默认字段、结果、文件副作用和限制。保持现有公开类名、根包导入和模块路径，没有为对齐主仓目录而改名；分类按表格行为和内部领域职责分别记录。
