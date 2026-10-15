# CodePilot project charter

## Objective

CodePilot is a repository-level Coding Agent. Given a software task, it must inspect a bounded repository, make a minimal code change, run verification, and report an auditable Git diff. Completion is established by explicit verification rather than by a model assertion.

The project prioritizes:

1. Engineering depth over feature count.
2. Evaluation over demo polish.
3. Problem-driven design over technology-name accumulation.
4. Measured results over unsupported claims.

## Fixed engineering decisions

- **Core harness:** CodePilot owns its Agent Loop, state, tool protocol, termination policy, and execution control. It must not use OpenHands, mini-SWE-agent, LangGraph Agent Executor, CrewAI, or AutoGen to implement that loop.
- **Initial platform:** Windows 10, Python 3.11, PowerShell, Git for Windows, and `E:\\Git\\bin\\bash.exe`. Phase 1 does not require WSL or Docker.
- **Provider abstraction:** The Agent Harness depends only on a provider-neutral interface and internal message/tool schemas. DeepSeek is the initial default provider, not a Harness dependency.
- **Configuration:** Runtime configuration is supplied through `.env` and typed config loading. Secrets are never committed or written to trajectories, run metadata, logs, or reports.
- **Default model settings:** Phase 1 uses a DeepSeek OpenAI-compatible endpoint configured by `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_SECONDS`, and `LLM_REQUEST_RETRIES`.
- **Two independent retries:** `LLM_REQUEST_RETRIES` retries transient provider/network failures only. Agent retry/repair is a later Agent-policy concern and must be tracked separately as `agent_max_retries`; provider retries must never be misreported as repair attempts.
- **Verification:** A model saying it is done never establishes success. Tests, compilation, a verifier, and/or an explicit success condition do.
- **Trajectory:** Store only task-relevant structured observations and short action summaries. Do not request, infer, parse, or persist private chain-of-thought.

## Phase 1 scope

Phase 1 builds a minimal, inspectable harness around one tiny Python bug repository:

- internal messages and run state;
- provider-neutral LLM interface;
- structured tool calling;
- Git Bash execution environment;
- workspace boundary and minimal permission policy;
- `list_files`, `read_file`, `search_text`, `edit_file`, and `bash` tools;
- test -> fix -> verify loop;
- trajectory and run metadata;
- max-step termination.

Explicitly out of scope: planning, repository retrieval, embeddings, skills, memory, MCP, multi-agent flows, Docker, ablations, browser/IDE agents, and web UI.

## Evaluation and safety direction

From Phase 2 onward, each benchmark task will define `task_id`, repository and buggy revision, issue text, success condition, visible tests, externally protected verifier/hidden tests, allowed files, and forbidden files. Runs will capture provider/model/configuration identity, prompt version, Git commit, timing, token/cost information when available, tool configuration, and agent limits.

Without Docker or a separate OS identity, Phase 1 can provide **logical isolation**, not a security sandbox. Hidden tests and evaluators must live outside the Agent workspace; tool-level paths will deny access to them. Strong isolation is postponed to a later environment phase and will be documented honestly.

## Change-control rule

Before adding any non-Phase-1 module, document: the observed problem, why the module addresses it, the cost of omitting it, how to test its value, and whether it belongs to Tool, Context, Planning, Skill, Control, Environment, or Evaluation.

