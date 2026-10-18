# Context Compaction V2 实验手册

## 1. 为什么要做第二轮

第一轮 `ledger-transfer-atomicity` A/B 中，两组都成功，但 `full`（压缩）比
`full-uncompacted`（完整历史）使用了更多 Token、更多 read_file 和更长时间。轨迹暴露了两个实验问题：

- 旧策略一旦 step 数超过 4 就会压缩，即使上下文只有约 9.7k 字符；较早源码被摘要后，模型可能重新读取；
- 未压缩组只在 `context_compaction` 事件中记录上下文大小，因此报告里的 0 是“未采集”，不是实际为 0；
- 单次 A/B 的轨迹在首次压缩前已经发生随机分叉，不能把全部差异归因于压缩。

V2 不是为了预设“压缩一定更好”，而是把问题变成可证伪实验。

## 2. V2 的唯一核心变化

```dotenv
AGENT_CONTEXT_TRIGGER_CHARS=16000
AGENT_CONTEXT_MAX_CHARS=32000
AGENT_CONTEXT_RECENT_STEPS=4
```

- 小于 16k 字符：不压缩，即使已经超过 4 个 step；
- 达到 16k：开始将较老的完整 action/observation step 变成公开规则摘要；
- 尽量不超过 32k；至少保留最新一个完整 tool-call / observation 对；
- `RunState.messages` 仍保留完整规范历史，不记录或总结隐藏 Chain-of-Thought。

`trigger` 解决“何时值得压缩”，`max` 解决“最多容忍多大”，`recent_steps` 解决“压缩后原样保留多少近期反馈”。三者不是同一个概念。

## 3. 实验问题与判定顺序

核心问题：在不降低任务成功率的前提下，V2 是否减少重复发送的上下文和输入 Token？

按以下顺序判断：

1. **正确性护栏**：`success_rate`、`test_pass_rate` 不能下降；
2. **主要效率指标**：`avg_input_tokens`、`avg_total_context_chars_sent`；
3. **遗忘/重读信号**：`avg_read_file_count`、`avg_steps`；
4. **次要指标**：`avg_total_tokens`、`avg_run_elapsed_ms`、`avg_llm_latency_ms`；
5. **机制检查**：`avg_context_compaction_count`、`avg_context_chars_saved`、逐 run trajectory。

字符数是 provider-neutral 近似值，输入 Token 是 Provider 返回的计费/用量数据。延迟受网络波动影响，证据强度低于成功率和 Token。

## 4. 控制变量

两组都使用 `full` Harness 能力：required planning、failure reproduction、lexical retrieval。唯一开关是：

- `full-uncompacted`：发送完整 action/observation 历史；
- `full`：启用 V2 context compaction。

Runner 按确定性的轮转顺序执行配置。例如同一任务重复三次时为 AB、BA、AB；下一个任务从 BA 开始。这样不能消除模型随机性，但能降低“某配置永远先跑”的顺序偏差。

## 5. 先做无 API 检查

在项目根目录运行：

```powershell
python run.py eval `
  --suite benchmarks\context_ablation_v2_suite.json `
  --config full-uncompacted `
  --config full `
  --repeat 3 `
  --dry-run
```

预期看到 2 个 task、2 个 config、3 次重复，共 12 个 case。`--dry-run` 不调用 DeepSeek。

## 6. 正式运行

```powershell
python run.py eval `
  --suite benchmarks\context_ablation_v2_suite.json `
  --config full-uncompacted `
  --config full `
  --repeat 3
```

这是 12 个真实 API case。若先控制费用，可做 6-case 预实验：

```powershell
python run.py eval `
  --task-file benchmarks\tasks\ledger-transfer-atomicity.json `
  --config full-uncompacted `
  --config full `
  --repeat 3
```

运行结束后把终端打印的 `evaluation_dir=...` 发给我即可。不要重复运行同一个输出目录；Runner 会自动创建带时间戳的新目录。

## 7. 如何查看结果

汇总报告：

```powershell
$evaluationDir = "把终端输出的 evaluation_dir 粘贴到这里"
Get-Content "$evaluationDir\report.md"
```

重新生成并打印报告（不会调用模型）：

```powershell
python run.py report "$evaluationDir"
```

查看某个 case 的轨迹：

```powershell
python run.py view `
  "$evaluationDir\ledger-transfer-atomicity\full\run-01\artifacts\trajectory.jsonl"
```

重点检查 `assistant_response` 事件中的：

```text
context_mode
context_compacted
context_chars_before
context_chars_after
context_steps_compacted
```

以及 `final_summary.json` 的：

```text
metrics.context_request_count
metrics.total_context_chars_sent
metrics.context_chars_saved
metrics.max_context_chars_before
metrics.max_context_chars_after
```

`total_context_chars_sent` 按 Harness 的 Provider 调用统计，不额外乘上 Provider 内部网络重试次数。

## 8. 什么结果才值得写进项目

- 若成功率持平且输入 Token 明显下降：可以写“阈值式工作上下文压缩降低重复上下文开销”；
- 若 Token 下降但重读/失败增加：说明摘要损失超过收益，应提高 trigger 或保留更多 step；
- 若几乎不触发压缩：任务仍不够长，只能说明短任务无需压缩；
- 若压缩仍更差：这也是有效结论，保留 full baseline，并把失败轨迹写入 limitation / failure analysis。

不要从 1 次 run 宣称百分比收益。当前 12-case 实验仍是小样本，应表述为“在自建可复现任务集上的观察”，不能泛化成生产级结论。

## 9. 已完成实验结果

### 默认16k校准

2 tasks × 2 configurations × 3 repeats 共12 cases，两组全部成功。compact 组没有发生压缩，因为最大
单轮上下文只有14,325字符。该轮证明 threshold gate 正常，不能用于计算压缩收益。

### 8k强制触发

8k仅通过进程环境变量临时覆盖，默认配置没有修改。结果如下：

| Context configuration | Strict success | Avg input tokens | Avg total tokens | Avg latency | Avg reads | Compactions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full history | 6/6 | 33,042 | 35,637 | 43.6s | 10.17 | 0 |
| Compact | 6/6 | **25,746** | **27,790** | **37.6s** | **8.83** | 14 |

compact 组累计上下文字符直接减少约4.9%，平均单轮峰值上下文降低约11.7%；端到端观察到输入 Token
降低22.1%、latency降低13.9%。后两个数字还包含较短模型轨迹与随机波动，不能全部视作 compaction
的因果收益。

逐轨迹检查发现 compact 组有5次重复读取、完整历史组有2次；两组 strict success 都是100%，且
compact 总读取次数仍更低。当前默认继续保持16k，8k只用于验证机制与观察激进压缩的权衡。
