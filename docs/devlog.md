# Development log

## Phase 1: minimal reliable harness

### Implemented

- Provider-neutral messages, tool protocol, and usage model.
- Typed environment configuration with secret-safe snapshots.
- DeepSeek OpenAI-compatible adapter with provider-only retry behavior.
- Workspace-bound file tools and an allow-listed Git Bash tool.
- Explicit verification outside the model control path.
- JSONL trajectory and redacted run metadata.
- A deterministic end-to-end test using a scripted Provider.

### Important design trade-offs

The edit tool performs a single exact replacement instead of free-form patch application. This is intentionally narrow: it makes accidental broad edits and ambiguous changes observable during the first learning phase. Unified diff patching is a later Tool-layer hypothesis, not a requirement for the minimal loop.

The command tool rejects shell operators and mutation by default. This means the Agent cannot use common one-line shell convenience such as chained commands. The cost is reduced flexibility; the benefit is a straightforward policy that can be unit tested before a sandbox exists.

### Current evidence

The deterministic integration test proves the code path:

    read_file -> failing pytest -> edit_file -> passing pytest -> Harness verification

It also sends a forbidden deletion command first and confirms that the command becomes a denied observation rather than a crashed run.

### Live DeepSeek smoke test

On 2026-09-04, the default DeepSeek configuration completed the isolated tiny-Python benchmark successfully.

- Provider/model: DeepSeek / deepseek-v4-flash.
- Terminal state: verified_success.
- Agent steps: 5 of a 12-step limit.
- Usage reported by the provider: 6,130 total tokens.
- Tool flow: list_files, read_file on the implementation and visible test, exact edit_file, pytest.
- Verification: 1 test passed; the Harness ran a separate final pytest verification after the model stopped calling tools.
- Git result: exactly one source-line diff changed return a - b to return a + b; git diff --check passed.

The provider returned no cost field, so run cost remains null rather than estimated. This is a smoke test, not an evaluation result: one trivial task cannot establish benchmark success rate.

### Trajectory readability update (2026-09-08)

The old trajectory stored assistant_response.action_summary from the ordinary assistant content field. Tool-calling turns commonly return no ordinary content, so most action summaries were null even though the following tool_result was complete.

The Harness now derives action_summary, action, reason, and targets from the already observable ToolCall name and arguments. It does not ask the model for a rationale and does not persist hidden reasoning. A lightweight terminal viewer was added:

    python -m codepilot.trajectory.viewer <trajectory.jsonl>

The viewer reads both standard JSONL and the historical pretty-printed object stream. A new isolated DeepSeek smoke run verified success in 5 steps, with all 5 assistant_response events having non-empty action summaries. Its trajectory was 5,676 bytes, compared with 6,175 bytes for the earlier run; no token is spent on the generated summary.

## Phase 2: reliable, evaluation-ready runs

### Day 1: Task Contract

Added TaskSpec JSON as the reproducible input format for a coding task. It records the task ID, issue, repository relative to the task file, verifier, allowed edit paths, visible tests, and whether reproduction is required. The existing direct CLI flags remain available for manual experimentation.

### Day 2: bounded reproduction and repair

For TaskSpec tasks that require reproduction, edit_file is denied until CodePilot has observed a non-zero pytest result. A final-verification failure now returns a concise verifier observation to the next LLM turn, up to AGENT_MAX_RETRIES. This is deliberately a linear bounded retry, not a planner or retry tree.

### Day 3: minimum public plan

Added update_plan, a small structured tool that records one to six public execution steps. The --require-plan mode rejects repository tools until the Agent has recorded a plan. The plan is an evaluation switch and trajectory artifact, not a complex planner.

### Known limitations

- Agent repair policy is represented in metadata but is not implemented in Phase 1; the normal action-observation loop is distinct from repair retries.
- Workspace and command policy provide logical isolation only. Docker or OS-level isolation is required before claiming a sandbox.

## Phase 3: repository context / lexical retrieval

### Day 1: bounded lexical baseline

Added a dependency-free `LexicalRepositoryRetriever` as an explicit `--retrieval-mode lexical`
experiment switch. It ranks readable, non-protected workspace files by task-token overlap, injects
bounded top-k excerpts into the first LLM turn as reference data, and records a step-0 retrieval event
plus retrieval configuration in run metadata. `none` remains the default baseline.

The retriever is deliberately not an embedding index: it provides an explainable lexical baseline for
the later no-retrieval versus retrieval comparison. Unit and integration tests verify relevance ranking,
protected-path exclusion, and first-turn context injection.

### Spring Boot retrieval benchmark

Added a sanitized 184-file, three-module Spring Boot benchmark copied from a local project. It excludes
runtime configuration, build/IDE artifacts, and source Git history. A focused JUnit test exposes a bug in
the shared `Result.success(payload)` factory and is verified with an offline Maven command. To support this
real task without broadening shell access, the command policy now permits only offline, module-scoped Maven
`test` commands with a named test class; the reproduction gate recognizes that same test family. Build output
directories such as `target` are protected from file tools and lexical retrieval.
