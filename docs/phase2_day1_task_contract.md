# Phase 2 Day 1: Task Contract

## Why this exists

Phase 1 direct CLI flags made the safety boundary visible, but they are awkward
and make experiments easy to misconfigure. A TaskSpec stores the same facts in
one reviewable JSON file: the issue, repository, verifier, allowed edit paths,
visible tests, and a stable task ID.

## Data flow

    TaskSpec JSON -> load_task_spec -> resolve_run_input -> Workspace/Harness

The Harness still receives ordinary task text and a verification command. This
is intentional: TaskSpec is input configuration, not a new abstraction inside
the Agent Loop.

## New command

    python -m codepilot.cli.main --task-file benchmarks/tasks/phase1_tiny_python_bug.json

The repository path is relative to the TaskSpec file. Direct flags remain
supported for manual experiments.

## Limitation

TaskSpec records requires_reproduction but does not enforce it yet. Day 2 will
make that policy observable and testable; recording the rule first lets future
evaluation tasks state it consistently.
