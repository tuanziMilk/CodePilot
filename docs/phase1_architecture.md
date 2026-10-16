# Phase 1 architecture: minimal reliable harness

## Goal and non-goals

The Phase 1 goal is a demonstrably autonomous loop on a tiny Python repository: inspect files, reproduce a failing test, make a bounded edit, rerun verification, and finish only after explicit success.

It deliberately does not plan, retrieve across large repositories, load skills, invoke MCP, run multiple agents, or provide a web UI. These are later hypotheses to evaluate, not presumed improvements.

## Architecture

```text
CLI task + Config
       |
       v
RunFactory -----> RunMetadata + TrajectoryWriter
       |
       v
AgentHarness <-----> RunState / Message history
       |
       | Provider-neutral ChatRequest (tool schemas included)
       v
LLMProvider (DeepSeekOpenAICompatibleProvider in Phase 1)
       |
       v
Internal ToolCall(s)
       |
       v
ToolDispatcher --> PermissionPolicy --> WorkspaceEnvironment
       |                                      |
       v                                      v
Internal ToolResult(s)                 Git Bash / repository files
       |                                      |
       +---------- Observation ----------+
                                          |
                                          v
                                   AgentHarness next turn
                                          |
                  verification pass / terminal failure / step cap
                                          v
                                  FinalReport + Git Diff
```

## Module responsibilities

| Module | Responsibility | Must not do |
|---|---|---|
| `cli` | Parse a task reference and launch a run. | Decide task success. |
| `config` | Load, validate, and redact settings. | Leak API keys into artifacts. |
| `models` | Define provider-neutral value objects. | Execute tools or API requests. |
| `agent.harness` | Own the turn loop, state transition, max steps, and terminal states. | Depend on DeepSeek SDK response objects. |
| `llm.base` | Define the provider-neutral completion interface. | Know workspace implementation details. |
| `llm.deepseek` | Translate DeepSeek OpenAI-compatible payloads to/from internal models. | Make Agent-policy decisions. |
| `tools` | Publish schemas and perform one bounded operation. | Bypass permission/environment checks. |
| `environment.git_bash` | Run approved commands using Git Bash at the workspace root. | Decide whether commands are allowed. |
| `permissions` | Validate paths and commands before execution. | Modify files or call the model. |
| `verification` | Run a declared success command and return an explicit result. | Treat model text as proof. |
| `trajectory` | Persist redacted, structured execution facts. | Persist private reasoning or secrets. |

## Turn data flow

1. The CLI loads a task and typed configuration, creates an immutable `RunMetadata`, and initializes `RunState` with the user task.
2. The harness creates a `ChatRequest` from public system instructions, task, previous model messages, and normalized tool observations. It includes the five JSON tool schemas.
3. A provider sends that request to DeepSeek and maps its structured response into internal `AssistantMessage` plus zero or more internal `ToolCall` values.
4. The harness logs a redacted action summary. For each requested tool, the dispatcher validates its arguments, permission policy, and workspace path before it invokes the tool.
5. The tool returns one normalized `ToolResult`, including status and an output summary. The harness appends a corresponding `ToolObservation` to state and trajectory.
6. The next LLM turn sees these observations and may call further tools. The loop ends only on a verified success, unrecoverable policy/tool/provider failure, or max-step limit.
7. The final report contains terminal status, verification result, Git diff summary, and artifact paths; it does not expose secrets or private reasoning.

## Internal protocol

### `ToolCall`

```python
@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, JSONValue]
```

- `call_id` is provider-generated when available; otherwise CodePilot creates one.
- `name` must exactly match a registered tool.
- `arguments` are JSON-object data validated by that tool's Pydantic input model before execution.

### `ToolResult`

```python
@dataclass(frozen=True)
class ToolResult:
    call_id: str
    tool_name: str
    status: Literal["ok", "error", "denied", "timeout"]
    output_summary: str
    data: dict[str, JSONValue]
    return_code: int | None
    duration_ms: int
```

`output_summary` is bounded/redacted text for the next model turn and trajectory. `data` holds tool-specific structured facts such as file names or match counts; it must not include API credentials, hidden-verifier contents, or unrestricted command output.

## DeepSeek mapping

`DeepSeekOpenAICompatibleProvider` is one implementation of `LLMProvider.complete(request) -> ChatResponse`.

| CodePilot internal concept | DeepSeek OpenAI-compatible representation |
|---|---|
| `SystemMessage`, `UserMessage`, `ToolObservation` | `messages` entries with `system`, `user`, and `tool` roles |
| Registered tool schema | `tools: [{type: "function", function: ...}]` |
| `ToolCall` | assistant `tool_calls[*].id`, `function.name`, parsed `function.arguments` |
| `ToolResult` | follow-up `tool` message with matching `tool_call_id` |
| Token / cost / latency | provider usage fields when returned; latency measured locally; cost nullable |

Malformed JSON, absent tool-call IDs, unsupported tool-call response formats, and transient HTTP/API errors are provider-normalization concerns. Transient request failures use `LLM_REQUEST_RETRIES`; a valid model request that chooses a bad action is an Agent/tool outcome and does not use that retry budget.

Before coupling the harness to any model behavior, Phase 1 includes a small provider contract test: send one simple tool schema, assert that a valid structured call is normalized, and assert that malformed/unsupported results fail with typed errors. If DeepSeek is unstable, only the adapter changes; the Harness contract stays fixed.

## Windows Git Bash environment

`GitBashEnvironment` receives an absolute workspace root and the configured Git Bash executable path. It executes a command with the workspace as the process working directory using a non-interactive invocation equivalent to `bash.exe -lc <command>`.

The environment returns captured stdout/stderr subject to byte and line limits, a return code, duration, and timeout status. It does not use string interpolation to construct a shell command; Python process arguments and an explicit working directory are used. The `bash` tool is therefore an environment adapter, while command authorization remains in `PermissionPolicy`.

## Workspace and minimum permissions

- Each run receives one resolved workspace root. All file-tool paths are canonicalized and must remain beneath it.
- File edits are limited to task-allowed paths, defaulting to ordinary source/config paths in the workspace.
- The Agent cannot read or edit configured forbidden paths: `.git` internals, evaluator/benchmark metadata, hidden tests, and other protected locations.
- The `bash` tool begins with a small allow-list for read/test commands (`pwd`, non-hidden `ls`, `rg`, `git diff`, `pytest`, and selected Python invocation). Mutating or destructive commands are denied by default.
- Commands containing dangerous operations such as recursive deletion, disk/registry operations, formatting, shutdown, or path escapes are denied. A command must be explicitly approved before it can run.
- Phase 1 protection is policy enforcement, not a security sandbox. It is deliberately called out in reports and architecture documentation.

## Trajectory and run metadata

Every run writes newline-delimited JSON events plus one redacted metadata record. Required event fields are:

```text
run_id, step, timestamp, event_type,
action_summary, tool_name, tool_arguments,
tool_result_summary, return_code, state_change,
verification_result, token_usage, latency_ms
```

`action_summary` is short, user-visible action-oriented text. For Phase 1 it is deterministically derived from the requested tool names and arguments, rather than requested from the model. The optional `action`, `reason`, and `targets` fields provide the same public decision record in a structured form. They are never a request for hidden reasoning. Sensitive configuration is excluded, `base_url` is recorded only as a non-secret identifier (for example, host name or configured provider alias), and token/cost data are nullable when unavailable.

Metadata additionally records provider, model, base-url identifier, temperature, max output tokens, request retry limit, agent step/retry limits, tool-policy version, prompt version, CodePilot Git commit, start time, aggregate token/cost/latency values, and terminal state. The final report also captures the bounded working-tree Git diff when the workspace is a Git repository.

## Proposed Phase 1 layout

```text
codepilot/
  src/codepilot/
    agent/           # harness, run state, terminal policy
    config/          # typed settings and secret redaction
    llm/             # base interface and DeepSeek adapter
    models/          # messages, tool protocol, events
    tools/           # tool schemas, dispatcher, five implementations
    environment/     # workspace and Git Bash execution adapter
    permissions/     # path and command policy
    verification/    # explicit success-command runner
    trajectory/      # event writer and metadata writer
    cli/             # command entry point
  tests/
    unit/
    integration/
    contract/
  benchmarks/
    repos/
      tiny_python_bug/
    tasks/
  docs/
  .env.example
  .gitignore
  README.md
  pyproject.toml
```

Only `README.md`, `docs/`, `.env.example`, and `.gitignore` are created before architecture approval. Source files and the benchmark repository are Phase 1 implementation work.

## Implementation checklist

- [ ] Initialize Python package, lint/test tooling, and Git repository.
- [ ] Add typed settings, `.env` loading, redacted config snapshot, and `.gitignore`.
- [ ] Implement internal message, state, `ToolCall`, `ToolResult`, and trajectory event models.
- [ ] Implement provider-neutral `LLMProvider` and DeepSeek OpenAI-compatible adapter.
- [ ] Add mocked provider contract tests and a manual DeepSeek structured-tool probe.
- [ ] Implement workspace resolver and permission policy with unit tests for traversal/protected paths/dangerous commands.
- [ ] Implement Git Bash adapter with timeout and bounded output.
- [ ] Implement five basic tools through a dispatcher and Pydantic schemas.
- [ ] Implement single-agent harness and max-step terminal policy.
- [ ] Create tiny Python bug benchmark and explicit verifier.
- [ ] Add integration test for inspect -> test -> edit -> test -> verified completion using a deterministic fake provider.
- [ ] Run an opt-in live DeepSeek smoke test after the API key is supplied locally.
- [ ] Write a Phase 1 demo and known-limitations note.

## Completion criteria

Phase 1 is complete only if:

1. A deterministic integration test drives the Harness through file inspection, a failing test, one edit, a passing test, and explicit verification.
2. The same flow works in a manually initiated live DeepSeek smoke run, or a provider incompatibility is captured by contract-test evidence without modifying Harness internals to accommodate it.
3. Path traversal, protected-path access, and representative dangerous command attempts are rejected and recorded as `denied`.
4. Provider request retries and Agent repair retries are distinct fields and never counted as one another.
5. All run artifacts are redacted, contain required metadata/events, and contain no API key or private chain-of-thought.
6. The Agent does not finish successfully without an explicit passing verification result.
7. Unit, contract, and integration tests pass on the Windows/Git Bash target environment.
