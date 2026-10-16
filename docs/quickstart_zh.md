# 操作手册：从离线验收到真实评测

## 1. 进入克隆目录

```powershell
Set-Location C:\path\to\codepilot
python run.py doctor
```

把示例路径替换为你的 Git clone。`doctor` 会显示实际导入的源码目录，应指向当前仓库的
`src\codepilot`。建议按 README 创建独立 `.venv`，不要依赖其他目录中的 editable install。

## 2. 无需 Key 的验收

```powershell
python run.py prepare
python run.py validate
python run.py demo
```

`prepare` 准备 15 个 Git repo、TaskSpec、外部 acceptance test 和 reference fix。已经存在且
干净的基线会复用；若你直接修改过它，命令会拒绝覆盖，保护你的文件。

`validate` 新克隆两个 workspace：baseline 保留 Bug，reference 应用已知修复，然后分别跑可见
测试与额外验收。这是 **4 次本地测试 / task**，证明题目可复现、可修复，不评价模型。结果保存在
终端显示的 `artifacts/benchmark_validation/.../validation_summary.json`。

`demo` 用固定动作的 Provider 演示真实工具执行，因此无需 API。它会打印 `artifact_dir`：

```powershell
python run.py view "<artifact_dir>\trajectory.jsonl"
```

你会看到失败测试、精准替换、测试通过、Harness 外部 verification。`provider=scripted-offline`
用来说明这条轨迹是工程流程演示，不能用于模型成功率统计。

## 3. 配置 DeepSeek

```powershell
Copy-Item .env.example .env
```

打开本目录 `.env`，填写 `LLM_API_KEY` 和真实 `LLM_MODEL`；默认 endpoint 为
`https://api.deepseek.com`。填写后无需把 Key 发给我。主要预算配置：

| 变量 | 作用 |
| --- | --- |
| `AGENT_MAX_STEPS` | 每次 run 最大模型轮数 |
| `AGENT_MAX_RETRIES` | 最终验证失败后可返回模型修复的次数 |
| `LLM_REQUEST_RETRIES` | 网络/HTTP 暂时失败的请求重试数 |
| `LLM_TIMEOUT_SECONDS` | 单次 API 请求超时 |
| `COMMAND_TIMEOUT_SECONDS` | 本地工具命令与 Harness verifier 超时 |

Provider retry 与 repair retry 不是同一个东西。新增版本会分别保留计数；一次 run 中普通工具失败
后模型再次尝试，也不自动算 repair retry。

## 4. 先试一道题

```powershell
python run.py eval --task-file benchmarks\tasks\addition-smoke.json --config basic --config full --dry-run
python run.py eval --task-file benchmarks\tasks\addition-smoke.json --config basic --config full
```

第一条仅显示计划，不调用 API；第二条启动 **2 个 Agent runs**。每个 run 都有多轮 API 请求，
不是总共只发 2 次请求。

Evaluator 每个 case 会先检查基线测试是否真的失败，然后启动 Agent，最后检查额外验收与 diff。
其目录如下：

```text
artifacts/evaluations/<time>/
  evaluation_summary.json
  report.json / report.csv / report.md
  <task>/<config>/run-01/
    workspace/                  # 全新故障基线 clone
    task.json                   # 不含外部验收路径的任务副本
    result.json
    baseline_visible_test.json
    baseline_acceptance.json
    acceptance_result.json
    changes.diff
    cli_stdout.txt / cli_stderr.txt
    codepilot_artifacts/<run>/
      run_metadata.json
      trajectory.jsonl
      final_summary.json
```

## 5. 运行整个任务集

先跑 basic/full，20 个 Agent runs：

```powershell
python run.py eval --suite benchmarks\suite.json --config basic --config full
```

先对 5 道 challenge 题做四组比较，共 20 个 Agent runs：

```powershell
python run.py eval --suite benchmarks\challenge_suite.json
```

完整 15 题是 60 个 runs：`python run.py eval --suite benchmarks\suite.json`。

每次运行都创建新时间戳目录，可重复执行，不用手动恢复源码。`--repeat 3` 表示每个 task/config
各运行三次。单次硬超时用 `--case-timeout` 控制，评估侧本地测试超时用 `--test-timeout` 控制。

## 6. 把结果交给我分析

```powershell
python run.py report "<evaluation_dir>"
```

把 `evaluation_dir` 路径发我即可。我会读取 JSON 与轨迹，判断成功率、过度修改、超时、检索噪声、
定位开销及模型终止行为。你不需要手动抄每一项 token 或 latency。

`test_pass` 表示额外验收通过；`success` 还要求 Harness verified_success、无越权修改及 diff 审计
通过。`max_steps` 即使修改正确也保留为失败。无数据的指标是 `null/n/a`，不是零成本。

## 7. 学习与交付顺序

先运行 Demo 并读一次 trajectory，再看 architecture.md；了解消息循环与门禁后，直接运行任务集。
对照 report 和某个失败 case，才能回答“这个 Harness 设计有什么收益和代价”。现阶段不需额外
通读框架文档。已冻结的真实数据和简历口径见 `evaluation_results.md` 与 `resume_and_demo.md`。
