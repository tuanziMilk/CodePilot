# 项目介绍、Demo 与简历

## 已能如实描述的版本

**CodePilot：可复现评估的 Coding Agent｜Python / Pydantic / Git / DeepSeek API**

- 独立实现 Provider 无关的 Agent Harness，支持结构化工具调用、消息状态更新、测试失败反馈、
  预算终止与外部验证；区分 API 请求重试与任务修复重试。
- 实现 Workspace 路径校验、命令白名单与精确编辑工具，输出逐步 trajectory、Git diff、
  token/latency 与工具错误记录，支持人工回溯。
- 实现 lexical repository retrieval 与四组实验开关，提供 15 个带固定 Git 故障基线、
  可见测试及额外验收的合成任务；Evaluator 自动克隆隔离工作区并输出 JSON/CSV/Markdown 报告。

正式运行后才能追加：“在 N 个任务、每组 R 次重复中，成功率由 A% 变为 B%，平均 token 改变 C%。”
如果没有稳定提升，可以写“通过消融比较识别可靠性控制的成本及检索噪声”等真实结论。

不要写“生产级 sandbox”“媲美 Codex”“SWE-bench 达到 X%”“检索显著提升”，除非另有相应证据。

## 3–5 分钟 Demo

1. 展示 issue 与故障 Git commit，说明每个 case 都从相同状态开始。
2. 运行 `python run.py demo` 展示本地闭环，明确说明它是 scripted Provider。
3. 配置 Key 后运行一个真实任务，展示模型选择工具、测试失败、最小修改、最终 verification。
4. 用 `python run.py view <trajectory.jsonl>` 展示工具参数、退出码、步骤与 token。
5. 打开 Evaluation 报告，解释 full 对简单题可能更贵、retrieval 可能无收益的原因。

## 应能解释的核心问题

- 为什么模型只提出 ToolCall，不能直接执行？程序分别校验了什么？
- ToolResult 如何成为下一轮 messages？一步能否包含多次工具执行？
- 路径 resolve/relative_to 如何处理路径逃逸？为何这不是 OS sandbox？
- 为什么 verified_success、可见测试通过和额外验收通过要分别记录？
- plan 的 off/required 有何区别？公开动作计划为何不是私有思维链？
- 2×2 配置能回答什么？为何不能单独证明 planning 的作用？
- 单个任务成功、一次检索命中，为什么不能证明整体性能提升？

看懂当前实现并能回答这些问题后即可准备项目面试；后续增强由真实失败案例驱动。
