# MVP 交付状态（2026-10-17）

CodePilot 已达到“可写入实习简历、可现场 Demo、可运行 Evaluation、能够解释核心设计”的求职 MVP
标准。`complete` 表示本轮约定功能交付完成，不表示生产级 Agent。

## 功能完成情况

- Provider-neutral Harness、结构化 ToolCall、消息状态与终止控制。
- Pydantic 校验、Workspace 边界、allowed/forbidden write、受限 Bash 与精确替换一次。
- 公开 Planning、失败复现门禁、external verification、failure feedback 与 bounded repair。
- 首轮 lexical retrieval、公开 action summary、JSONL trajectory 与 pretty viewer。
- prompt `mvp-v2`：明确 plan 参数形状，并在 LLM step limit 后执行一次无额外模型行动的最终验证。
- 独立 baseline clone、额外 acceptance、tracked/untracked diff audit 与聚合报告。
- 21 个合成任务（含 6 个多文件 hard-v2 任务）、四个配置、离线 scripted demo 和统一 `run.py` 入口。

## 工程验收

| 检查 | 结果 |
| --- | --- |
| Ruff | All checks passed |
| pytest | 107 passed |
| Benchmark definition/reference validation | 21/21 validated |
| Challenge baseline/reference validation | 5/5 validated |
| Hard-v2 baseline/reference validation | 6/6 validated |
| Scripted offline demo | verified_success |
| 5-task challenge live evaluation | 20/20 cases success |
| 2-task × 3-repeat robustness evaluation | 24/24 cases success |
| Hard-v2 mvp-v2 candidate live evaluation | 24/24 cases success |
| Permission / diff audit | 所有 live cases 通过 |

已冻结评测使用的源码 commit 为 `e6a2f5128222753ca2d805c602be27004a1cb844`。其后新增 hard-v2
benchmark 与多文件检索报告指标，尚未追溯并入旧实验数字。详细数字见
[evaluation_results.md](evaluation_results.md)。

## 已知限制

- 合成任务仍有 100% 成功率天花板，样本量不足以证明一般化提升。
- hard-v2 已完成 24/24 候选真实模型运行；因为运行时 worktree 含未提交改动，正式发布前仍建议从
  clean commit 重跑，以让源码 provenance 可由 commit 完整重建。
- hard-v2 首轮探索结果发现并修正了三处 issue/acceptance 契约不对齐；旧数字不作为最终排名。
- Workspace boundary 是逻辑隔离，不是 OS sandbox。
- Retrieval 只有 lexical run-start snapshot，没有 embedding、AST 或增量更新。
- 编辑器只支持精确替换一次；工具能力有意保持小而可审查。
- 没有 Multi-Agent、MCP、Memory、Docker、IDE/Web UI。

## 发布前人工检查

- 确认 `.env`、`artifacts/`、`.idea/` 与 `benchmarks/repos/` 未被 Git 跟踪。
- 在 GitHub 页面检查 Mermaid、表格和相对链接渲染。
- 根据个人开源意愿选择并添加许可证；项目当前不替用户预设许可证。
- 创建公开仓库后，将 README 的 `<your-repository-url>` 换成真实 clone URL。
- 不上传包含本机绝对路径或 API Key 的历史 artifacts。
