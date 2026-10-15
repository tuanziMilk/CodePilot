# CodePilot Phase 4 学习手册：Evaluation 与项目化

## 1. Phase 4 解决什么问题

前 3 个阶段证明了 CodePilot 有 Agent loop、有限工具、验证、可靠性门禁和 retrieval；但单次
Demo 不能证明这些设计有效。Phase 4 的目标是把“某次跑成功”变成可复现的实验记录。

这里的最小单位不是一次模型调用，而是一个 **case**：

```text
TaskSpec + 固定 initial_commit + 一个 configuration + 一次独立运行
```

同一 case 只能在干净 Git baseline 上运行一次。否则前一个 Agent 的修改会污染后一个配置，比较无效。

## 2. 四个实验配置

| 配置 | `update_plan` | reproduction gate | retrieval |
| --- | --- | --- | --- |
| `basic` | 否 | 否 | none |
| `reliable` | 是 | 是 | none |
| `retrieval` | 否 | 否 | lexical |
| `full` | 是 | 是 | lexical |

它们不是四个不同 Agent；是同一个 Harness 的四组显式开关。这样可以比较 planning/reproduction 与
retrieval 各自的边际影响。每组仍保留 Workspace、Permission、精确替换和外部 verifier。

## 3. Evaluator 做了什么

入口是 [runner.py](../src/codepilot/evaluation/runner.py)。每个 case 会：

```text
读取 TaskSpec
  ↓
git clone task repository 到 evaluation artifact 内的新 workspace
  ↓
git checkout --detach initial_commit
  ↓
写入仅将 repository 改为 workspace 的 case-local TaskSpec
  ↓
以公开 CLI 启动 CodePilot，并传入 configuration 开关
  ↓
保存 CLI 输出、trajectory、final_summary、Git changed files、git diff --check
  ↓
汇总 evaluation_summary.json
```

clone 只复制已提交的 baseline，不会把源 benchmark 工作目录的未提交改动带入 case。Evaluator 不会替
你调用模型；只有你运行下述命令时，才会按 `.env` 调用 Provider。

## 4. 如何运行第一条任务

先从一个 task 和两个 configuration 开始，避免一次消耗过多 API token：

```powershell
Set-Location E:\AIProjects\Vibecoding\codepilot

python -m codepilot.evaluation.runner `
  --task-file benchmarks\tasks\phase2_tiny_python_bug.json `
  --config basic `
  --config full
```

输出目录默认在 `artifacts/evaluations/<UTC timestamp>/`。其中：

- `evaluation_summary.json`：按配置的汇总指标；
- `<task_id>/<config>/run-01/result.json`：单次 case 的结构化结果、实际 configuration 和脱敏 run metadata；
- 同目录 `workspace/`：该 case 的独立 Git 工作区；
- `codepilot_artifacts/<run_id>/`：原始 trajectory、metadata、final summary；
- `cli_stdout.txt` / `cli_stderr.txt`：方便定位 CLI 级错误。

增加 `--repeat 3` 才会为每个 configuration 运行三次；这会产生真实 Provider 调用与 token 消耗。

## 5. 应如何读指标

优先级如下：

1. `verified_successes / runs`：唯一严格成功率；源码 diff 看起来正确但 `max_steps` 不能算成功。
2. `git_diff_check_passed` 与 `changed_files`：是否只做了干净、允许的修改。
3. `avg_steps`、`tool_denied`、`tool_errors`：Harness 是否制造无效循环或工具摩擦。
4. `avg_total_tokens`、`avg_llm_latency_ms`、`avg_run_elapsed_ms`：成本与速度。

一次运行只能作为轨迹案例。至少应先有 5 个任务、每组相同任务集，再讨论平均成功率；有预算时再做
`--repeat 3`，从而区分稳定趋势和单次模型随机性。
