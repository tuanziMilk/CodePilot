# CodePilot — 可复现的 Coding Agent 求职 MVP

CodePilot 用自建 Python Harness 执行仓库定位、失败复现、精确编辑、测试与外部验证。
模型通过结构化 ToolCall 提出动作，程序负责校验、执行、记录和判定成功；支持 DeepSeek 等
OpenAI-compatible Chat Completions 接口。此目录是独立版本，原 `../codepilot` 保持原样。

当前交付包含完整运行代码、10 个自包含 Python 任务、四组实验配置、额外验收测试、报告生成和
离线 Demo。**当前版本的真实 LLM 成功率尚未测量**；脚本 Demo 和参考修复验证不代表模型性能。

## 开始使用

在 PowerShell 中切换目录。`run.py` 明确使用本目录的 `src`，不会误用以前全局安装的旧 CodePilot。

```powershell
Set-Location E:\AIProjects\Vibecoding\codepilot_complete
python run.py doctor
python run.py prepare
python run.py validate
python run.py demo
```

以上步骤在本地运行，不调用模型。`prepare` 将任务源码初始化为独立 Git 故障基线；`validate`
检查故障基线确实失败、参考修复通过可见测试与额外验收。`demo` 用预设动作执行真实工具和测试，
展示完整 trajectory；它明确标记为 scripted demo。

需要安装依赖时，建议使用本目录的虚拟环境，避免影响旧项目：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 配置模型并运行

```powershell
Copy-Item .env.example .env
```

编辑本目录 `.env` 中的 `LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`，其他配置已有默认值。
旧项目的 Key 不会被复制到这里。`LLM_PROVIDER=deepseek` 是默认标识；其他兼容服务同样由
`LLM_BASE_URL` 和 `LLM_MODEL` 指定。不同服务的 tool calling 兼容性需要实测。

先查看将运行哪些实验，再执行两组小样本：

```powershell
python run.py eval --suite benchmarks\suite.json --config basic --config full --dry-run
python run.py eval --task-file benchmarks\tasks\addition-smoke.json --config basic --config full
```

每个 case 都从 `initial_commit` 新克隆；已修复的 workspace 不会复用。第二条命令会产生真实
API 调用与费用。确认流程后运行全部任务、四组配置：

```powershell
python run.py eval --suite benchmarks\suite.json
```

默认是 10 tasks × 4 configs × 1 repeat；重复试验可加 `--repeat 3`。同一批结果比较时须保持
模型、预算、prompt、工具策略与任务集相同。

## 查看与解释结果

Evaluator 在终端输出 `evaluation_dir`。报告与轨迹入口：

```powershell
python run.py report "<evaluation_dir>"
python run.py view "<artifact_dir>\trajectory.jsonl"
```

JSON 保留逐轮 token、退出码、耗时、动作和工具结果；viewer 同时显示检索、工具状态、验证和
终止。最终报告统计成功率、测试通过、平均 steps、retry、token、latency、工具错误和拒绝。
缺失值不会伪装成 0；`cost=null` 表示服务没有提供可用费用数据。

| 配置 | Planning | 修改前失败复现 | Lexical retrieval |
| --- | --- | --- | --- |
| basic | off，工具不提供 | off | off |
| reliable | required | on | off |
| retrieval | off，工具不提供 | off | on |
| full | required | on | on |

这是“可靠性控制组合 × retrieval”的 2×2 比较。仅凭这四组不能单独识别 planning 与
reproduction 各自的因果收益；也不能凭一次成功宣称检索有效。

## 代码与文档

- [最短操作手册](docs/quickstart_zh.md)：具体命令、生成目录和学习顺序。
- [架构与核心设计](docs/architecture.md)：Provider、状态、工具、权限、验证与日志的职责。
- [任务说明](docs/benchmark_catalog.md)：10 道合成任务的症状、难度和局限。
- [实验协议](docs/evaluation_protocol.md)：基线、验收、指标与可比较性。
- [失败分析](docs/failure_analysis.md)：此前真实运行揭示的问题及本版修正。
- [简历与 Demo 讲解](docs/resume_and_demo.md)：可直接使用的事实描述与待实测数字。

旧 Phase 1–4 学习文档保留作实现过程参考；其中历史目录和配置不一定对应本版本，操作以本 README
和 quickstart 为准。

## 验证与边界

```powershell
python run.py test -q -p no:cacheprovider
python -m ruff check src tests
```

精确替换一次的编辑策略保持不变；不包含 unified diff、Docker、MCP、Multi-Agent、Embedding
或 IDE/Web UI。Workspace 与命令策略提供逻辑边界，**不构成 OS sandbox**。运行测试和项目构建
本身可以执行项目代码，因此仅用于可信本地 benchmark。API Key 不写入项目或轨迹；文件工具与
retrieval 拒绝 `.env`，日志不记录模型私有 reasoning。公开计划与动作摘要不等于私有思维链。

任务均为我们编写的合成练习，难度标签是人工相对分级，不能等同 SWE-bench 难度；额外验收与参考
答案在 Agent workspace 外，但无 OS 隔离时不能声称对恶意代码实现强隔离。
