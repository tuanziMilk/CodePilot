# MVP 交付状态（2026-10-16）

此目录是独立于旧 `../codepilot` 的求职版本。目录名中的 complete 指约定 MVP 的功能交付，
不表示生产级 Agent，也不表示已经得到真实模型的完整性能结论。

## 已完成

- Provider 无关 Harness、结构化 ToolCall、状态循环与模型请求重试。
- Pydantic 校验、Workspace、明确 forbidden write、受限 Bash 与精确替换一次。
- 公开 plan 的 off/optional/required、失败复现门禁、验证失败反馈与 bounded repair。
- 首轮 lexical retrieval 与可解释轨迹，始终记录命令退出码。
- 基线 clone 隔离、额外验收、tracked/untracked 审计、独立结果与聚合报告。
- 10 个回归任务、5 个 challenge 任务及四组实验配置；没有复制私有 Spring 项目。
- 相同公开 Plan 更新成为可观测 no-op；报告新增工具调用与 Retrieval 命中指标。
- 统一 run.py、离线 Demo、操作文档、架构、失败分析及简历讲解素材。

## 本次工程验收

| 检查 | 实际结果 |
| --- | --- |
| 源码与测试 Ruff | All checks passed |
| pytest 单元/协议/集成测试 | 103 passed |
| 15-task 候选基线与参考修复验证 | 15/15 validated |
| 正式 challenge suite 验证 | 5/5 validated |
| 每个任务的四个测试阶段 | baseline visible/acceptance 失败；reference visible/acceptance 通过 |
| 参考修复验证后的源仓库 | 全部保持 clean |
| 本地 scripted Demo | verified_success，7 steps，0 tool error/denied |
| Challenge Evaluation dry-run | 5 tasks × 4 configs × 1 repeat = 20 cases |
| 已有真实 Provider 实验 | 旧 10 题 × 4 configs = 40/40 success；新增 challenge 尚待实测 |

证据保存在 `artifacts/benchmark_validation/` 与 `artifacts/demos/`。这些是本机验收产物，
未跟踪进 Git；任何新机器都可以运行 prepare、validate、demo 重建证据。基线生成固定内容、
作者身份、时间与 SHA-1 object format，保留每题完整 commit hash。

本机账户和 sandbox 账户不同。为便于用户直接运行，最终 `benchmarks/repos` 已在本机账户下
重新生成相同 commit；sandbox 的生成副本留存在 `artifacts/sandbox_baselines`，未修改全局
Git safe.directory 或旧项目。若从 Git 克隆本项目，运行 prepare 即可创建属于当前账户的基线。

## 下一轮真实模型实验

旧 10 题单次实验出现 100% 天花板效应，同时发现重复 Plan 和 permission denial 的效率问题。
当前版本已修复 Plan 计数并加入 5 道 challenge 题。下一步运行 `benchmarks/challenge_suite.json`
的 20 cases；正式结果需保留失败、成本与样本数，不得把本地参考答案验证或 scripted Demo
计入模型 Evaluation。
