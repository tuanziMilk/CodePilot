# CodePilot Phase 1 学习与操作手册（零基础版）

> 面向第一次亲手实现 Agent 的开发者。默认你会一点 Python，做过 Java 或 Spring Boot 项目，但不假设你了解 Agent、RAG 或 MCP。

## 0. 先看结论：Phase 1 做成了什么

Phase 1 不是“全能编程助手”，而是 CodePilot 的最小发动机：一个真实可运行、可检查、可验证的 Coding Agent 闭环。

它已经能够：

1. 接收自然语言任务。
2. 调用 DeepSeek，并接收结构化 Tool Calling 响应。
3. 查看受限仓库的文件、搜索文本、精确修改一个文件、运行受限测试命令。
4. 将工具执行结果交还给下一轮模型，让模型连续行动。
5. 不相信模型的“我修好了”，而是由 Harness 独立运行 verifier。
6. 保存 trajectory、脱敏 metadata 和 Git diff。
7. 拒绝路径逃逸、测试篡改和代表性的危险命令。

真实 DeepSeek smoke test 的行为是：

    list_files
    -> read_file(calculator.py, test_calculator.py)
    -> edit_file(calculator.py)
    -> pytest
    -> Harness 再次 pytest 验证
    -> verified_success

它还没有、且当前故意不加入：

- Planning
- Repository Retrieval、Embedding、RAG
- Skill、Memory、MCP
- Multi-Agent、Docker、Web UI
- 正式多仓库 Benchmark 与消融实验

一个诚实的缺口：真实模型虽然修复成功，但没有在编辑前先主动运行失败测试。它读完实现和测试后直接修改，再运行测试。这说明“Prompt 建议”不等于“系统强制”；是否必须先复现失败再编辑，是进入 Phase 2 前要收尾的 Control 策略问题。

## 1. 最重要的心智模型：Agent 不是聊天机器人

普通聊天是：

    你提问 -> 模型回答 -> 结束

Coding Agent 是：

    你给任务
    -> 模型决定下一步动作
    -> 程序真实执行该动作
    -> 程序把结果交还给模型
    -> 模型继续行动
    -> 系统根据验证结果结束

把它类比为一个非常谨慎的实习生：

| 概念 | 人话解释 | 在 CodePilot 中 |
|---|---|---|
| LLM | 会理解文本和代码、能决定下一步的大脑。 | DeepSeek。 |
| Tool | 实习生被授予的一种具体能力。 | 读文件、改文件、跑测试。 |
| Environment | 工具真正工作的地点。 | Git Bash 和当前仓库。 |
| PermissionPolicy | 安全审批人。 | 判断动作是否允许。 |
| Harness | 管理实习生工作节奏的主管。 | AgentHarness。 |
| Verifier | 验收人员。 | VerificationRunner。 |
| Trajectory | 工作日志。 | trajectory.jsonl。 |

最关键的关系是：

    LLM 提议动作
    不等于
    动作一定执行

模型只能提出 ToolCall；只有经过 Dispatcher、PermissionPolicy 和 Environment 的动作才会真正执行。

## 2. 必须掌握的 12 个词

| 词 | 人话解释 |
|---|---|
| LLM | 大语言模型服务，例如 DeepSeek。 |
| Provider | 对某个模型 API 的适配层。 |
| Harness | 控制 Agent 多轮循环的程序，不是模型。 |
| State | 当前任务已经知道什么、做到哪一步。 |
| Message | 放进模型上下文的一条信息。 |
| Tool Calling | 模型输出结构化的工具请求，而不是只输出文字。 |
| Tool | Agent 获准执行的一种操作。 |
| Environment | Tool 最终在哪里运行。 |
| Permission | 对路径、命令和编辑范围的安全规则。 |
| Observation | 工具执行后返回给模型的信息。 |
| Verification | 系统独立确认任务是否真正成功。 |
| Trajectory | 一次 run 的结构化过程日志。 |

Phase 2 会遇到但暂未实现的两个词：

- Retrieval：从大仓库中挑出相关文件和代码，避免把整个仓库塞进模型。
- Benchmark：一组固定、可重复、可验证的任务，用于比较 Agent 设计。

## 3. 一次任务如何在代码中流动

先记住下面这条主链路：

    CLI
    -> Settings
    -> AgentHarness
    -> LLMProvider
    -> ToolCall
    -> ToolDispatcher
    -> PermissionPolicy
    -> Workspace / Git Bash
    -> ToolResult
    -> AgentHarness 下一轮
    -> VerificationRunner
    -> Final summary + Trajectory + Git diff

### 3.1 从命令行进入

入口：[cli/main.py](../src/codepilot/cli/main.py)。

它的角色类似 Spring Boot 的启动与装配层：

1. 从 .env 读取模型、超时、步数限制等设置。
2. 创建 Workspace，规定 Agent 可以访问哪个仓库。
3. 创建 GitBashEnvironment，规定命令在哪里执行。
4. 创建 PermissionPolicy，规定哪些动作必须拒绝。
5. 注册五个基础工具。
6. 把这些具体组件交给 AgentHarness。

这里可以知道当前 Provider 是 DeepSeek；但 AgentHarness 本身不应该知道。这种“具体组件只在最外层连接”的位置叫 composition root。好处是以后改 Provider 时，不会把 DeepSeek 的细节扩散到核心循环。

### 3.2 Harness 是项目的核心

打开 [agent/harness.py](../src/codepilot/agent/harness.py)，重点读 AgentHarness.run。

它的伪代码是：

    初始化 system message 和 user task
    重复执行，最多 max_steps 次：
        把当前 messages 和工具 schema 发给 Provider
        得到 assistant message

        如果模型请求工具：
            Dispatcher 执行 ToolCall
            把 ToolResult 变成 tool observation
            追加回 messages
            继续下一轮

        如果模型不再请求工具：
            运行 verification command
            测试通过 -> verified_success
            测试失败 -> verification_failed

    超过步数 -> max_steps

这就是 Agent “自主多步行动”的最小定义。先读懂它，再学 LangGraph、SWE-agent 或任何 Agent 框架会容易得多。

### 3.3 Provider abstraction 在解决什么

对照 [llm/base.py](../src/codepilot/llm/base.py) 和 [llm/deepseek.py](../src/codepilot/llm/deepseek.py)。

DeepSeek 的原始返回会包含 tool_calls、function.name 和 JSON 格式的参数。CodePilot 不让 Harness 直接解析这些 Provider 专属字段，而是在 adapter 里把它们变成内部对象：

    ToolCall(
        call_id="call-3",
        name="edit_file",
        arguments={"path": "calculator.py", "...": "..."}
    )

Harness 此后只认识 ToolCall。未来更换 OpenAI 或其他兼容 Provider 时，改的是 adapter，不是 Loop。

这是一条非常通用的工程原则：第三方 API 的不稳定格式停留在边缘，不污染你的核心业务逻辑。

### 3.4 Tool、Permission 和 Environment 为什么必须分开

以 bash 为例：

    BashTool：接收 command 参数。
    PermissionPolicy：判断该 command 是否允许。
    GitBashEnvironment：在 workspace 中执行已允许的 command。

如果它们混在一个类中，会很难测试，也容易出现绕过权限的路径。当前项目选择保守策略：只允许检查、测试、Git diff/status 等命令；拒绝 shell 串联、删除、网络下载、磁盘操作和受保护目录访问。

## 4. ToolCall 和 ToolResult：模型与真实世界的协议

模型不能直接写你的文件；它只能提出结构化请求：

    ToolCall(
        call_id="call-3",
        name="edit_file",
        arguments={
            "path": "calculator.py",
            "old_text": "return a - b",
            "new_text": "return a + b"
        }
    )

代码位置：[models/protocol.py](../src/codepilot/models/protocol.py)。

一个 ToolCall 必须满足：

1. name 是已注册工具。
2. arguments 能通过 Pydantic 参数校验。
3. 执行前通过路径和命令权限校验。

工具执行后返回 ToolResult：

    ToolResult(
        status="ok",
        output_summary="Updated calculator.py with one exact replacement.",
        data={"path": "calculator.py", "replacements": 1},
        return_code=None,
        duration_ms=1
    )

output_summary 给下一轮模型阅读；data 给程序、测试和未来评测使用。两者都要限长，否则一份巨大的日志会吃光模型上下文。

## 5. 为什么 edit_file 采用“精确替换一次”

编辑工具位于 [tools/file_tools.py](../src/codepilot/tools/file_tools.py)。

它不是接收整份文件再覆盖，而是要求 old_text 在文件中恰好出现一次，然后只替换一次。

这对复杂修改不够灵活，但在 Phase 1 有刻意价值：

- 修改范围小，容易审查。
- 找不到 old_text 或出现多次时，工具会拒绝而不是猜。
- 默认不能修改测试路径。
- 你可以清楚看到模型到底改了哪一行。

以后若要加入 unified diff patch，先问四件事：

1. 当前精确替换具体在哪些任务上导致失败？
2. diff patch 怎样解决？
3. 新风险是什么，例如 patch 冲突或大范围误改？
4. 如何通过 benchmark 验证成功率真的提升？

## 6. Verification：为什么测试要跑两次

真实 run 中，模型修改后已经跑过一次：

    pytest test_calculator.py -q

当模型停止调用工具、说自己修好了，Harness 仍会运行 CLI 中声明的 verifier：

    python -m pytest -q

第二次是 final verification。它表达的是：

    模型停止行动
    不等于
    任务成功

只有 verifier 的退出码是 0，terminal state 才是 verified_success。

面试时可以这样解释：

> 我把模型输出视为控制信号而非成功证明。Agent 停止后由 Harness 独立执行任务定义的 verifier，并用可观测的 return code 决定 terminal state。

## 7. 如何查看真实 trajectory

每次 run 的 artifacts 位于：

    <workspace>/.codepilot/runs/<run_id>/

三个重要文件：

| 文件 | 应该看什么 |
|---|---|
| run_metadata.json | Provider、模型、温度、步数限制、Git 基线和 retry 设置。不会有 API Key。 |
| trajectory.jsonl | 每行一个 JSON event：模型回复、工具结果、验证结果。 |
| final_summary.json | 终止状态、token 汇总、artifact 路径、Git diff。 |

当前真实运行的目录：

    .codepilot/live-smoke/.codepilot/runs/2874a5c2217141ab89831a1c8fc0c365

直接查看：

    Get-Content .codepilot/live-smoke/.codepilot/runs/2874a5c2217141ab89831a1c8fc0c365/run_metadata.json
    Get-Content .codepilot/live-smoke/.codepilot/runs/2874a5c2217141ab89831a1c8fc0c365/trajectory.jsonl

人类友好版查看：

    $run = Get-ChildItem .codepilot/live-smoke/.codepilot/runs -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
    Get-Content "$($run.FullName)/trajectory.jsonl" | ForEach-Object {
      $event = $_ | ConvertFrom-Json
      "step=$($event.step) type=$($event.event_type) tool=$($event.tool_name) state=$($event.state_change) code=$($event.return_code) verify=$($event.verification_result)"
    }

阅读顺序：

1. 找 assistant_response：这一轮模型是否要调用工具。
2. 看紧跟的 tool_result：真实程序返回了什么。
3. 看 return_code：测试命令 0 是成功，非 0 是失败。
4. 最后看 verification：成功必须由它证明，不能只看模型总结。

### 7.1 新版可读摘要与 viewer

模型请求工具时常常不输出普通文本，因此旧 trajectory 的 assistant_response 会有空的 action_summary。现在 Harness 会只根据可观察的 ToolCall 名称和参数生成简短摘要，例如 read_file(calculator.py) 会变成 inspect_files，目标是 calculator.py。

这不是模型的隐藏推理，也不会要求模型额外写解释，因此不会增加模型 token。它只是程序对已经发生的公开动作的标签。

使用 viewer 查看任意新旧 trajectory：

    python -m codepilot.trajectory.viewer <trajectory.jsonl>

旧日志仍然有效；没有新字段时 viewer 会标明它只能从 tool_result 推断意图。

查看实际补丁：

    git -C .codepilot/live-smoke diff --check
    git -C .codepilot/live-smoke diff
    git -C .codepilot/live-smoke status --short

不要只看模型总结。一个合格的 Coding Agent run 至少要同时看：diff、测试输出、final verification 和 trajectory。

## 8. 你自己如何测试 CodePilot

### 8.1 不消耗 API 的工程测试

这些测试验证我们的程序，而不是 DeepSeek 是否聪明：

    $env:PYTHONDONTWRITEBYTECODE='1'
    python -m ruff check --no-cache .
    python -m pytest -p no:cacheprovider

想只看核心闭环：

    python -m pytest tests/integration/test_harness.py -vv -p no:cacheprovider

该测试使用 ScriptedProvider，也就是“假模型”。它故意先请求危险删除命令，之后读文件、跑失败测试、修改、重测、验证。其意义是：网络断开或模型升级时，Harness 仍然能被确定性验证。

### 8.2 消耗 API 的真实 smoke test

不要直接修改原始 benchmark。先复制一份：

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $workspace = ".codepilot/manual-smoke-$stamp"
    New-Item -ItemType Directory -Force -Path $workspace | Out-Null
    Copy-Item -Path "benchmarks/repos/tiny_python_bug/*" -Destination $workspace -Recurse -Force
    git -C $workspace init
    git -C $workspace config user.name "CodePilot Smoke"
    git -C $workspace config user.email "codepilot-smoke@local"
    git -C $workspace add .
    git -C $workspace commit -m "buggy baseline"

    python -m codepilot.cli.main --task "The add function returns the wrong result. Locate the defect, fix only calculator.py, run the supplied tests, and finish only when ready for explicit verification." --workspace $workspace --verify-command "python -m pytest -q" --allowed-edit-path "calculator.py"

完成后用第 7 节的方法检查 metadata、trajectory、diff 和 verifier。

### 8.3 真实模型不要只跑一次

LLM 存在随机性。temperature=0 会减少差异，但不保证完全一致。Phase 1 建议重复 3 次同一 smoke task，并记录：

    run_id
    terminal_state
    steps
    total_tokens
    是否先复现失败测试
    diff 是否只修改 allowed_files
    verification 是否通过

这还不是正式 benchmark，但它会训练你用证据而不是 Demo 看 Agent。

## 9. 进入 Phase 2 前应该学什么

不要试图先学完整个大模型领域。下面顺序足够，而且每项都能立刻回到 CodePilot 代码。

### 第一层：Python 工程基础

学习：

1. pathlib：为什么要解析真实路径，如何防止 ../ 路径逃逸。
2. subprocess：为什么 Git Bash 用显式 argv 与 cwd，而不是 shell=True。
3. dataclass 和 Pydantic：前者适合轻量内部对象，后者适合外部输入校验。
4. JSON 与异常：模型 arguments 为什么必须 parse、validate 并返回 typed error。

资料：

- [Python pathlib 官方中文文档](https://docs.python.org/zh-cn/3.11/library/pathlib.html)
- [Python subprocess 官方中文文档](https://docs.python.org/zh-cn/3.11/library/subprocess.html)
- [Pydantic Models 文档（英文）](https://docs.pydantic.dev/latest/concepts/models/)

完成标志：你能解释 Workspace.resolve 为什么同时要用 resolve 和 relative_to。

### 第二层：测试、Git 和可验证修改

学习：

1. pytest 的断言、测试发现规则和退出码。
2. Git working tree、commit、status、diff。
3. 为什么“测试通过”后仍要看 diff。
4. visible tests 和 hidden verifier 的区别。

资料：

- [pytest 官方中文文档](https://docs.pytest.org/zh-cn/stable/)
- [Pro Git 中文版](https://git-scm.com/book/zh/v2)

完成标志：你能独立创建一个小 Bug Repo，写出 Bug 和测试，运行 CodePilot，再判断它有没有作弊或过度修改。

### 第三层：LLM API 与 Tool Calling

学习：

1. HTTP 请求、超时、429、5xx 和网络重试。
2. system、user、assistant、tool 四类 message。
3. JSON Schema：如何告诉模型工具参数格式。
4. Provider retry 与 Agent repair retry 为什么不能混。

资料：

- [DeepSeek API 官方中文文档](https://api-docs.deepseek.com/zh-cn/)
- [DeepSeek Function Calling 官方中文文档](https://api-docs.deepseek.com/zh-cn/guides/function_calling)

完成标志：你能从 [deepseek.py](../src/codepilot/llm/deepseek.py) 指出请求 JSON 在哪里生成、tool_calls 在哪里变成内部 ToolCall、坏 JSON 在哪里被拒绝。

### 第四层：Agent 工程思维

学习：

1. State：每轮结束要保存哪些事实。
2. Observation：为什么工具输出应限长、脱敏、结构化。
3. Control：最大步数、终止条件、失败处理为什么属于 Harness。
4. Evaluation：单次 Demo 为什么不是成功率。
5. Failure taxonomy：失败是定位错、计划错、工具错，还是模型能力限制。

资料：

- [Hugging Face Agents Course 中文版](https://huggingface.co/learn/agents-course/zh-CN/unit0/introduction)

完成标志：你能回答：

    Agent Loop 在哪里？
    ToolResult 如何回到下一轮模型？
    模型为什么不能直接运行 shell？
    API 超时重试与任务修复重试有什么区别？
    为什么模型说完成不能作为成功条件？
    一次成功 Demo 为什么不等于 Agent 很强？

## 10. 进入 Phase 2 前的结业清单

- [ ] 打开真实 trajectory，按 step 解释每一个 event。
- [ ] 从 cli/main.py 开始，沿调用链读到 ToolResult 回到 Harness。
- [ ] 独立运行一次无 API 的 integration test。
- [ ] 独立运行一次真实 smoke test，并查看 Git diff。
- [ ] 故意让 Agent 请求受保护路径或危险命令，确认结果是 denied。
- [ ] 用自己的话解释 Provider retry 和 Agent repair retry。
- [ ] 和我一起决定是否将“编辑前必须先复现失败测试”提升为 Harness 强制策略。

做完这些，你不需要成为 Agent 专家；但你已经具备进入 Phase 2 的基础：知道每个新模块属于哪一层、解决什么问题，以及怎样验证它真的有效。
