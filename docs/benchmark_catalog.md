# 第一版任务集与本地验收

这 15 道题由本项目生成，都是合成 Python 仓库，不包含原 Spring 项目或其他个人业务代码。
只依赖 Python 标准库与 pytest，执行 `python run.py prepare` 后即可使用。

| Task ID | 层级 | 主要行为 | 仓库实现模块 |
|---|---|---|---:|
| addition-smoke | smoke | 加法回归，确认 loop/evaluator 可运行 | 1 |
| email-case | easy | 邮箱本地部分大小写保留与非法地址 | 1 |
| pagination-boundary | easy | 分页切片、末页、空列表与校验 | 1 |
| cache-expiry | medium | TTL 到期边界、缓存更新与 session 调用 | 3 |
| inventory-reservations | medium | 多购物车行按 SKU 累加，阻止超卖 | 4 |
| config-falsy-overrides | medium | 区分 key 不存在和显式 false/0/空/null | 4 |
| intervals-open-boundary | medium | 半开区间重叠合并与相邻区间区分 | 3 |
| money-half-up | medium | Decimal 舍入规则与聚合后统一舍入 | 3 |
| audit-nested-redaction | hard | 字典/列表递归脱敏且不修改输入 | 4 |
| query-repeated-values | hard | 多文件请求路径中重复查询参数保序 | 5 |
| atomic-batch-reservation | challenge | 批量库存的聚合校验与事务原子性 | 5 |
| dependency-cycle-order | challenge | 稳定拓扑排序、共享依赖与环检测 | 5 |
| payment-idempotency-conflict | challenge | 幂等键载荷冲突与失败重试状态 | 5 |
| profile-event-versioning | challenge | 乱序、重复、冲突与缺口事件投影 | 5 |
| retry-error-classification | challenge | 永久/瞬态错误分类与精确重试预算 | 5 |

层级是任务内部的相对分类，不意味着达到真实工业项目的 hard 难度。前 10 题用于稳定回归；
challenge 题增加跨文件契约、状态不变量和隐藏边界，但仍保持单一根因与短参考修复。多文件题
保留有业务作用的兄弟模块，不以复制无关文件制造难度。
问题描述给出预期行为，不直接给出待修改源码路径。`allowed_files` 列出仓库的全部实现
源文件，避免只有一个可写文件时由权限失败直接暴露答案。

## 生成和验证

在项目根目录执行：

```powershell
python run.py prepare
python run.py validate
```

`prepare` 为每题创建独立 Git 仓库，固定作者时间、局部 Git identity 和故障 commit。
它输出 `benchmarks/suite.json` 与带完整 `initial_commit` 的 TaskSpec。重复执行会检查
已有 baseline 与当前定义一致；遇到源码修改会拒绝覆盖。需要重新生成时可指定全新路径：

```powershell
python -m codepilot.benchmarks.prepare --output benchmarks_new
```

生成结果：

```text
benchmarks/
  suite.json                 # 全部 15 题
  challenge_suite.json       # 5 道较难题
  tasks/*.json             # Agent 任务和 evaluator 元数据
  repos/<task_id>/         # 含 Bug、visible test 和 .git 的独立 baseline
  acceptance/*_test.py     # 独立验收，不在 Agent workspace
  reference/*.json         # 参考修复，不在 Agent workspace
```

`validate` 每题创建两个独立 clone；在 baseline 上分别运行可见测试与外部验收，均应
观察到断言失败；在 reference clone 应用参考修复，再运行两套测试，均应通过。它不调用
任何模型，原 baseline 源码保持干净，输出位于 `artifacts/benchmark_validation/<时间>/`。
`validation_summary.json` 和同名 Markdown 记录每道题四次检查及源仓库状态；测试原始输出
分别保存在各题目录中。外部验收使用独立 pytest 进程与 workspace 的 PYTHONPATH，验收文件
不会复制到 Agent clone 内。

## 什么算通过

可见测试是 Agent 能自行发现和读取的反馈。外部 acceptance 是 evaluator 的额外验收，
覆盖输入边界和已有行为，Agent 的 workspace 工具无法访问这些文件。参考修复用于证明
题目可解，不是模型结果，也不会被 evaluator 作为模型补丁使用。

仅有 visible test 通过不等于整个任务通过；正式报告应同时记录 Agent 的终态、可见测试
验收、外部 acceptance 和修改范围审计。外部测试虽对 Agent 不可见，但源码在公开项目中，
并非保密测试集，因此报告应称其“外部验收”，避免夸大为未见过的公共榜单。

本任务集规模小、Python 为主、缺少真实 issue 修复历史；目前适合初步比较配置成本与
具体失败原因。不能据此声称达到 SWE-bench 或生产环境能力，也不能保证 retrieval 有收益。
如果模型在小仓库直接 list/search 就定位到目标，应如实报告检索开销和零收益。
