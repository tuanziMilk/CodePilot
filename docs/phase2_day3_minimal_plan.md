# Phase 2 Day 3: minimal public planning

## What changed

Planning is one update_plan tool. It accepts one to six short public steps,
stores them in RunState, and writes plan_version and plan_steps into trajectory
events. With --require-plan, repository tools are denied until the model records
that plan.

## Why this is enough for the MVP

This is an experimental switch, not a planner graph. It lets evaluation compare
the same task set with planning disabled or enabled, while retaining a clear
trajectory of what the Agent announced before acting.

## Limitation

The Harness does not automatically decide when to replan. The model may call
update_plan again after a failure, and each successful call creates a new plan
version. Automatic plan branching is intentionally out of scope.
