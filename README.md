# dataflow-embodied

独立维护的 DataFlow 具身扩展，当前实现版本为 **0.1.3**。主要功能是把采集文件中已有的步骤标签和时间区间整理成 `subtasks.json`；此外还提供 episode 清理、S2 参考约定的 LeRobot v2.1 导出与校验。

安装后通过 `import dataflow_embodied` 注册算子，与 DataFlow 的 Storage 和 Pipeline 组合使用。无需把源码复制进 DataFlow 主仓。

子任务转换读取 `joints.jsonl` 或 `manifest.json` 中已有的标签，不理解视频内容、不调用模型，也不会凭空生成步骤描述。清理和 LeRobot 导出是另一条独立流程。

## WebUI 运行与处理前后对比

已通过官方 DataFlow-WebUI 的 **Save & Run → Ray** 执行采集检查和已有步骤标签转换，未添加自定义界面或接口。示例从铜板采集记录导出 12 段 `subtasks.json`，没有调用模型。截图中的本机文件路径已遮挡。

![官方 WebUI 中实际执行具身扩展](docs/assets/embodied-webui.png)

下面的对比图展示 `joints.jsonl` 中已有的步骤标签，以及实际生成的 `subtasks.json` 全部 12 段和起止时间。视频帧用于帮助查看原始采集画面，不代表模型识别。本图未演示清理及 LeRobot 导出。

![采集记录到 subtasks.json 的前后对比](docs/assets/embodied-before-after.png)

WebUI 加载方式是在后端安装本包、将 `dataflow_embodied` 加入 `_DATAFLOW_EXTENSIONS` 并重启。视频和关节文件须可被后端访问。再次运行时为 `EmbodiedSubtaskExporter` 设置新的 `output_dir`，已有导出不会被覆盖。

## 已有步骤标签转为 subtasks.json

调用方可以直接把 episode 路径交给 `EmbodiedSubtaskExporter`：

```python
from dataflow_embodied import EmbodiedSubtaskExporter

result = EmbodiedSubtaskExporter("artifacts/subtasks").transform({
    "path": "/data/episode_001",
    "task_text": "搬运铜板",  # 可选；不填时保留来源任务文本
})
print(result["subtasks_path"])
```

它读取 `joints.jsonl` 中已有的标签或 `manifest.json` 中的步骤，保留时间区间与来源，不调用模型，也不编写新的动作说明。输出位于 `output_dir/<来源标识>/subtasks.json`，包含标签和起止时间，并保持待复核状态。没有已有标签或可靠时间基准时会报错；不会覆盖已有文件。

## 算子契约与字段安全

每个公开算子的 `get_desc("zh")` / `get_desc("en")` 包含初始化参数、实际默认字段、结果结构和错误行为。`run` 新增结果列并保留输入行数、顺序和源列；**输出列必须尚不存在**，已有同名列时在处理前报错，请换一个 `output_key`。旧代码若依赖覆盖列，需要显式改用新列。

`Pipeline.compile()` 检查表格字段依赖；来源字典的内部字段、文件是否存在和媒体内容在运行时检查。编译成功不代表这些外部资源已经通过校验。

## 安装

在扩展仓库目录内使用 Python 3.10–3.12 安装：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

## 本地离线示例与开发验证

离线示例自行生成小型合成 episode，演示 DataFlow Pipeline、FFmpeg 和 Parquet 的清理与导出流程；它用于展示文件结构，不代替真实业务数据验收。输出目录必须尚不存在。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m dataflow_embodied.pipelines.demo --output artifacts/my-demo
python -m pytest -q
```

依赖固定 `open-dataflow==1.0.11` 和 `pyarrow==20.0.0`；imageio-ffmpeg 提供媒体工具。本机验证结果和未覆盖的平台见 [验证说明](docs/VALIDATION.md)。`requirements-macos-py312.txt` 是 macOS arm64 本地环境锁定文件。

## 输入与示例产物

以下输入和产物说明针对清理与 LeRobot 导出 Pipeline。

清理 Pipeline 的输入是 JSONL，每行含一个 `episode` 描述。例如：

```json
{"episode":{"path":"/data/episode_001","task_text":"已确认的机器人任务描述","confirm_subtasks":true,"confirm_derived_action":true}}
```

`path` 指向已有的本地来源载荷。确认字段应在核实子任务及动作定义后填写；本包默认不自动确认。来源格式、特征约定、质量门限和拒绝行为见 [数据契约](docs/CONTRACT.md)。

上面的离线示例会产生：

| 文件或目录 | 用途 |
|---|---|
| `input.jsonl` | 本次示例 episode 清单 |
| `run/steps/embodied_step1.jsonl` | 逐 episode 清理计划 |
| `run/steps/embodied_step2.jsonl` | 导出状态、位置和报告 |
| `run/parts/` | 逐 episode 产物 |
| `dataset/` | 最终合并的 LeRobot v2.1 数据集，含 Parquet、视频及元信息 |
| `summary.json` | 最终 episode 数、帧数及校验结果 |

这些路径相对 `--output` 目录。`finalize_dataset` 必须在全部批次结束后执行一次，不能在每个 batch 中提前合并。

| 算子 | 作用 |
|---|---|
| EmbodiedDatasetInspector | 识别来源和报告数据载荷 |
| EmbodiedSubtaskExporter | 将已有子任务标签转换为独立的 `subtasks.json` |
| EmbodiedCleaningPlanner | 产生清理区间、时钟映射和质量报告 |
| EmbodiedLeRobotExporter | 验证显式确认并导出单个 episode |
| EmbodiedDatasetValidator | 校验最终数据集 |

算子 `run(storage, input_key=..., output_key=...)` 保留原列，默认隔离运行故障；质量拒绝单独记录。导出需要明确的任务和相关确认，不默认批准推导动作。非空输出不覆盖；本包未实现中断续跑或重复执行幂等文件事务。

## 清理与 LeRobot 导出

另一路 Pipeline 用于检查已有 episode、生成清理计划、导出单个 episode，并在所有批次完成后合并和校验 LeRobot v2.1 数据集。可运行的离线示例和完整输入字段见上文及 [数据契约](docs/CONTRACT.md)。

## 首版支持边界

支持已核对的本地 S2 载荷，以及符合原运行时 **S2 特征约定、单任务 v2.1** 的 LeRobot 数据。只含标签的来源可检查，缺少状态/视频时不可物化。不承诺任意机器人、任意多任务数据集或 v3.x。清理门限、参考特征和媒体限制详见契约。

不依赖 Sandbox 镜像、EDP 或 Pyromind；不调用模型，不提供平台任务提交、HTTP API 或 TS SDK。第三方代码来源与适配说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [LICENSE](LICENSE)。
