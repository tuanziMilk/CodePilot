# Trajectory example：一次被 verifier 救回的修复

这个案例来自 `dependency-cycle-order/basic/run-02` 的真实模型运行。任务要求部署顺序在遇到可达依赖
环时抛出 `DependencyCycleError`。下表是 JSONL trajectory 的人工可读摘要；只包含公开动作、工具
参数/结果和状态，不包含也不尝试还原模型的隐藏 Chain-of-Thought。

| Step | Observable action | Tool / result | State |
| ---: | --- | --- | --- |
| 1 | 查看仓库文件 | `list_files(.)` | tool_ok |
| 2 | 阅读目标实现与测试 | `read_file` × 4 | tool_ok |
| 3 | 阅读调用方和 README | `read_file` × 4 | tool_ok |
| 4 | 尝试组合 Shell 命令 | `cd . && git log ...` 被策略拒绝；随后 `search_text` 成功 | tool_denied → tool_ok |
| 5 | 复现问题 | `python -m pytest -q` → `DID NOT RAISE DependencyCycleError` | return_code=1 |
| 6 | 模型未编辑便停止 | Harness 独立执行同一 verifier，仍失败 | verification_failed_retrying |
| 7 | 接收失败反馈后重新检查 | `read_file(deploy/planner.py)` | tool_ok |
| 8 | 添加 DFS 环检测 | `edit_file` 精确替换一次，引入 `in_progress` 集合 | tool_ok |
| 9 | 验证修复 | `python -m pytest -q` → `1 passed` | return_code=0 |
| 10 | 模型结束 | Harness 再次独立验证 | verified_success |

关键转折对应的结构化日志类似：

```json
{
  "step": 6,
  "event_type": "verification",
  "tool_name": "verification",
  "return_code": 1,
  "state_change": "verification_failed_retrying",
  "verification_result": false,
  "retry_count": 0
}
```

Harness 随后增加 `repair_retry_count`，把命令、退出码和有界失败摘要作为新的 user observation 送回
Agent。修复完成后最终事件为：

```json
{
  "step": 10,
  "event_type": "verification",
  "tool_name": "verification",
  "return_code": 0,
  "state_change": "verified_success",
  "verification_result": true,
  "retry_count": 1
}
```

这个案例展示了三件事：

1. 测试失败本身只是 observation，不会自动令 Agent run 终止；
2. 模型的普通结束消息不能绕过 external verifier；
3. Agent repair 发生在任务结果不合格之后，与 Provider 网络请求重试不同。

可用自己的 API 配置重新生成同类轨迹：

```powershell
python run.py eval `
  --task-file benchmarks\tasks\dependency-cycle-order.json `
  --config basic

python run.py view "<artifact_dir>\trajectory.jsonl"
```

模型行为具有随机性，新 run 不保证在同一步提前结束；Evaluation 的意义正是保留这种差异，而不是
要求每条轨迹复刻固定脚本。
