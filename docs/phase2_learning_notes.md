# CodePilot Phase 2 学习手册：让 Agent 的成功更可信

> 本手册对应当前的最小 Phase 2 实现：TaskSpec、失败复现门禁、有限修复重试、公开计划。
> 它不是一套新的 Agent 理论课；阅读代码、运行一次实验、看 trajectory 即可完成本阶段学习。

## 1. Phase 2 在项目中的位置

Phase 1 回答的是：**模型如何经由受控工具修改一个仓库？**

Phase 2 回答的是：**一次“看起来修好了”的运行，怎样变成可复现、可约束、可解释的实验？**

它仍然是单 Agent、单工作区、5 个基础文件/命令工具。新增的不是“更聪明的模型”，而是 Harness 的四条可靠性控制：

    TaskSpec
        -> 先复现失败
        -> 允许最小编辑
        -> 外部验证失败时给反馈并有限重试

可选的 `update_plan` 在最前面记录一份公开计划。它帮助审计与实验比较，但不读取或存储模型的隐藏 reasoning。

## 2. 先记住这张责任表

| 问题 | 负责组件 | 为什么不能只相信模型 |
| --- | --- | --- |
| 这次任务允许改哪些文件、怎么验收？ | `TaskSpec` | 自然语言 prompt 容易遗漏或被误解。 |
| 编辑前是否真的见过故障？ | `AgentHarness` | 模型可能直接猜一个修改，恰好让 visible test 通过。 |
| 模型宣布完成后是否成功？ | `VerificationRunner` | “我完成了”不是程序正确性的证据。 |
| 验收失败后还要不要继续？ | `AgentHarness` 的 retry budget | 防止无限循环，也不把一次失败直接当终局。 |
| 这轮打算做什么？ | `update_plan` tool + trajectory | 保留简短、可公开的行动计划，而不是 Chain-of-Thought。 |

一个很重要的界线：**prompt 是给模型的建议；Harness policy 是程序实际执行的规则。**

## 3. TaskSpec：把一次任务变成可复现合同

代码在 [task.py](../src/codepilot/models/task.py)。一个最小任务文件如下：

```json
{
  "task_id": "email-normalize-lowercase",
  "repository": "../repos/email_bug_phase2",
  "issue_description": "Fix email normalization so it trims whitespace and lowercases addresses.",
  "verification_command": "python -m pytest -q",
  "allowed_files": ["email_utils.py"],
  "visible_tests": ["test_email_utils.py"],
  "forbidden_files": ["test_email_utils.py"],
  "requires_reproduction": true
}
```

字段含义：

- `task_id`：稳定实验编号。以后聚合 Evaluation 时，不能靠一段自然语言来识别任务。
- `repository`：相对**任务 JSON 文件所在位置**的仓库路径，而不是相对当前 PowerShell 目录。这使任务文件移动到另一台机器时仍有清楚的含义。
- `issue_description`：真正给模型看的问题描述。
- `verification_command`：Harness 最后独立执行的验收命令。
- `allowed_files`：`edit_file` 能写入的最小集合。
- `visible_tests`、`forbidden_files`：目前主要是任务声明；`forbidden_files` 不应同时出现在 `allowed_files`。它们也为 Phase 4 的“有没有改测试作弊”检查留下证据。
- `requires_reproduction`：是否要求 Agent 在编辑前先看到一次失败的、已授权测试命令。

`TaskSpec` 使用 Pydantic 校验外部 JSON。它拒绝绝对 `repository` 路径、`../` 形式的 allowed path，以及允许/禁止列表重叠。注意：这不是唯一安全边界；真正路径防逃逸仍由 `Workspace.resolve()` 负责。

从命令行到 Harness 的路径是：

    task.json
      -> load_task_spec()
      -> resolve_run_input()
      -> Workspace(allowed_write_paths=...)
      -> harness.run(issue_description, verification_command, ...)

入口在 [main.py](../src/codepilot/cli/main.py)。这也解释了 TaskSpec 的定位：它是**可审查的运行配置**，不是另一个 Agent Loop。

## 4. Failure feedback：为什么要“先失败，再编辑”

在 Phase 1 的 calculator / email demo 中，模型可以读测试后直接改代码。结果正确，但它未必真的定位并复现了问题。

Phase 2 对 `requires_reproduction=true` 的任务新增如下门禁：

```text
Agent 请求 edit_file
        |
Harness 是否已经观察到“模型调用 bash 跑已授权测试，且退出码非 0”？
        |
   否 -> 返回 ToolResult.denied，不写文件
   是 -> Dispatcher 执行 edit_file
```

对应实现是 [harness.py](../src/codepilot/agent/harness.py) 的 `_execute_call()` 与 `_observe_test_failure()`。

这里的“观察到”非常具体：目前识别 `pytest ...`、`python -m pytest ...`，以及受限的离线 Maven
测试命令（例如 `mvn -o -pl <module> -Dtest=<TestClass> test`；安全参数可按常见顺序出现），并且要求该
**bash tool call** 返回非零码。它不是在猜模型是否“理解了 bug”。

这仍是有意的 MVP 限制：我们只因真实 Spring benchmark 增加了离线 Maven test。JavaScript 的 `npm test`、任意编译失败、服务端健康检查，后续由真实任务需要再扩展；现在不要提前把“任意测试命令识别器”做复杂。

## 5. 两种 retry：发生的位置不同

| 类型 | 发生在哪 | 处理的失败 | 是否重新调用同一个 API 请求 |
| --- | --- | --- | --- |
| Provider retry | `DeepSeek...Provider` | 超时、网络错误、429/5xx 等模型服务问题 | 是，重发尚未得到有效响应的请求。 |
| Agent repair retry | `AgentHarness` | 模型结束工具调用后，外部 verification 仍失败 | 否，给模型一条新的“验收失败”观察，让它决定下一步。 |

第二种的控制流是：

    LLM 不再请求 tool
      -> VerificationRunner.verify()
      -> 失败且 retry_count < AGENT_MAX_RETRIES
      -> 写入 verification_failed_retrying trajectory event
      -> 向 state.messages 加一条公开的失败反馈
      -> 下一轮 LLM

因此它不是“自动把上一步再执行一遍”。模型会拿到命令、退出码、截断后的输出，重新检查、修改、测试。超过预算时，terminal state 是 `verification_failed`；超过总轮数则是 `max_steps`。

`AGENT_MAX_RETRIES` 与 `LLM_REQUEST_RETRIES` 分别在 `.env` 管理。为了观察 repair retry，可把前者设为 `1`；不要把它设很大，MVP 中一次修复机会足够比较策略。

## 6. 最小 Planning：公开行动摘要，不是隐藏推理

`update_plan` 定义在 [plan.py](../src/codepilot/tools/plan.py)。模型最多提交 6 步、每步最多 240 个字符，例如：

```json
{
  "steps": [
    "Inspect the implementation and its tests.",
    "Run the focused test to reproduce the failure.",
    "Apply the smallest allowed fix and rerun verification."
  ]
}
```

传入 `--require-plan` 后，第一条非 `update_plan` 的工具请求会得到 `ToolResult.denied`。成功计划存入 `RunState.plan_steps`，每次更新时 `plan_version` 加一，并附加到后续 trajectory event。

它只回答“准备做什么、涉及什么对象、为什么”，不要求模型展示逐 token 思考或私有推理。面试中可以这样说：

> 我把 planning 设计成受 schema 约束、可记录的 tool，而没有收集模型 reasoning。它既能作为可审计的运行状态，也可以作为 Evaluation 的实验开关；但当前版本不做 planner graph，也不自动 replan。

## 7. 一次完整 Phase 2 run 应该长什么样

使用 `--task-file` 和 `--require-plan` 时，理想 trajectory 的因果顺序是：

```text
Step 1  update_plan
        -> plan_version=1，记录公开计划
Step 2  bash: python -m pytest ...
        -> return_code != 0，reproduction_failure_observed=true
Step 3  edit_file (仅 allowed_files)
        -> 精确替换一次
Step 4  bash: python -m pytest ...
        -> 测试通过
Step 5  模型停止请求工具
        -> Harness 的 VerificationRunner 再运行 verification_command
        -> verified_success
```

如果 Step 5 的独立验证失败，则会多出一次 `verification_failed_retrying` event 与下一轮模型调用；这个轨迹比“模型说完成”更有说服力。

所有事件仍在 `trajectory.jsonl`，机器读取字段没有删除；可以继续使用：

```powershell
python -m codepilot.trajectory.viewer <某次运行目录的trajectory.jsonl>
```

重点找：`return_code`、`verification_result`、`retry_count`、`plan_version`、`plan_steps`、以及 `tool_denied`。它们对应的都是 Harness 可观察的事实，而非模型私有推理。

## 8. 你的最短动手检查点（约 30–45 分钟）

不要从头读所有源码。下面使用仓库自带的 `tiny_python_bug` 模板。**不要直接让
Agent 修改模板本身**；先复制出一个独立实验目录，这样可以反复重做，也不会污染后续
benchmark。

### 0. 一次性准备：定义这次实验的路径

打开 PowerShell，复制下面四行。`$` 开头的是 PowerShell 变量；它们只在当前窗口
有效，不会修改系统环境变量。

```powershell
$projectRoot = "E:\AIProjects\Vibecoding\codepilot"
$templateRepo = Join-Path $projectRoot "benchmarks\repos\tiny_python_bug"
$exerciseRepo = Join-Path $projectRoot "benchmarks\repos\phase2_tiny_python_bug"
$exerciseTask = Join-Path $projectRoot "benchmarks\tasks\phase2_tiny_python_bug.json"
```

如果 `phase2_tiny_python_bug` 已经存在，请把上面两个 `phase2_tiny_python_bug` 名称
同时改成一个新名字（例如 `phase2_tiny_python_bug_v2`）；不要删除旧实验目录。

### 1. 复制故障 repo，并确认它确实失败

下面命令会复制 source/test 模板，并创建一份指向新 repo 的 TaskSpec。最后一行只是
在 JSON 中替换 repository 路径；可用记事本打开 `$exerciseTask` 检查这一处。

```powershell
Copy-Item -Recurse $templateRepo $exerciseRepo
Copy-Item "$projectRoot\benchmarks\tasks\phase1_tiny_python_bug.json" $exerciseTask
(Get-Content -Raw $exerciseTask).Replace("../repos/tiny_python_bug", "../repos/phase2_tiny_python_bug") |
    Set-Content -NoNewline $exerciseTask

Set-Location $exerciseRepo
python -m pytest -q
```

预期最后一条命令显示 1 个失败测试，并且 PowerShell 的 `$LASTEXITCODE` 为非 0。可用
下面命令确认：

```powershell
$LASTEXITCODE
```

它不应为 `0`。如果显示 `0`，说明你没有在新目录中运行，或 bug 已被改掉；此时不要
继续运行 Agent，换一个新的实验目录再复制一次。

### 2. 固定 Git 故障基线，并查看 TaskSpec

仍在 `$exerciseRepo` 中执行：

```powershell
git init
git add calculator.py test_calculator.py
git commit -m "buggy baseline"
git status --short
```

最后 `git status --short` 没有输出，表示工作区干净。若 `git commit` 提示没有配置
身份，只需在这一个实验 repo 运行一次：

```powershell
git config user.name "Your Name"
git config user.email "you@example.com"
git commit -m "buggy baseline"
```

然后从项目根目录查看这份合同：

```powershell
Set-Location $projectRoot
Get-Content $exerciseTask
```

你应当看到：`repository` 指向 `../repos/phase2_tiny_python_bug`、`allowed_files` 只有
`calculator.py`、`forbidden_files` 包含 `test_calculator.py`，以及
`requires_reproduction: true`。

### 3. 运行带公开 Planning 的 Phase 2 Agent

仍在 `$projectRoot` 执行：

```powershell
python -m codepilot.cli.main --task-file $exerciseTask --require-plan
```

`--task-file` 表示使用 TaskSpec，而不是手工输入 `--workspace`、`--verify-command` 等
一串参数；`--require-plan` 则开启“先调用 `update_plan`，才能操作 repo”的 Harness
门禁。终端最后会打印 JSON summary，其中最重要的是：

```text
terminal_state: "verified_success"
verification_passed: true
plan_version: 1 或更大
artifact_dir: 本次 run 的证据目录
```

模型具有概率性，因此不把一次运行当作绝对保证。若得到 `max_steps` 或
`verification_failed`，先保留该 artifact；它同样是后续分析 Agent failure 的有效实验
结果，不要直接覆盖或删除。

### 4. 读 trajectory，并用 Git 检查它没有过度修改

先取得刚刚创建的最新 artifact 目录，再运行 viewer：

```powershell
$runDir = Get-ChildItem "$exerciseRepo\.codepilot\runs" -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
python -m codepilot.trajectory.viewer (Join-Path $runDir.FullName "trajectory.jsonl")
```

接着检查真实文件改动：

```powershell
Set-Location $exerciseRepo
git diff -- calculator.py
git status --short
python -m pytest -q
```

理想情况下，diff 只会把 `calculator.py` 中的 `return a - b` 改为 `return a + b`。
`git status --short` 可能还显示未跟踪的 `.codepilot/` 和 `__pycache__/`：前者是
CodePilot 的运行证据，后者是 pytest 的缓存，它们都不是业务代码修改。

最后在 trajectory viewer 输出中依次回答：

1. 是否先有 `update_plan`？若模型先请求其他工具，是否有对应 `tool_denied`？
2. `edit_file` 之前，是否有 `bash: python -m pytest ...` 的非零 `return_code`？
3. `edit_file` 是否只指向 `calculator.py`？
4. 最终 verification 的 `verification_result` 是否为 `true`？

如果你还想专门观察 repair retry：故意让 TaskSpec 的 `verification_command` 比模型自行运行的测试更严格（例如多跑一个隐藏测试），然后将 `.env` 的 `AGENT_MAX_RETRIES=1`。预期是第一次最终验证失败、Harness 写入反馈、模型获得一次受限修复机会。实验结束后恢复正确的任务配置；不要为了“让 Agent 成功”去改测试。

## 9. 只需读的代码顺序

1. [main.py](../src/codepilot/cli/main.py)：输入如何组成实际运行。
2. [task.py](../src/codepilot/models/task.py)：TaskSpec 如何限制外部 JSON。
3. [harness.py](../src/codepilot/agent/harness.py)：门禁、状态、验证和 retry 在哪里发生。
4. [plan.py](../src/codepilot/tools/plan.py)：公开计划为何只是普通 Tool。
5. [test_reliability_controls.py](../tests/integration/test_reliability_controls.py) 与 [test_minimal_planning.py](../tests/integration/test_minimal_planning.py)：不调用真实 API，也能读懂控制规则为何被验证。

## 10. Phase 2 完成标志

你不必背源码。能用自己的话说明下面五件事，就可以进入 Phase 3：

- TaskSpec 与 prompt 的区别：前者约束和复现实验，后者告诉模型要解决什么。
- 为什么“先复现失败再编辑”必须由 Harness 执行，而不是只写在 system prompt。
- Provider retry 与 Agent repair retry 的边界。
- `update_plan` 为什么不是 Chain-of-Thought，以及它如何帮助比较实验。
- 一条从 `tool_denied` / 失败测试，到修复、外部验证、`verified_success` 的 trajectory。

## 11. 当前刻意未做的内容

- 自动 planner、任务分解树、反思/自我批评循环；
- 任意语言/任意测试框架的失败识别；
- 自动生成隐藏测试；
- 复杂 permission UI、Docker sandbox、MCP、Multi-Agent。

这些都可能有价值，但不是当前求职 MVP 的 Phase 2 完成前置条件。
