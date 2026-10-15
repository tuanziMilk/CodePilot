# Phase 2 Day 2: Reproduction and bounded repair

## New control rules

For a TaskSpec with requires_reproduction=true, CodePilot denies edit_file until it
has observed a non-zero return code from a model-requested, allow-listed test command.
The denial is returned as an ordinary ToolResult, so the model can adapt rather
than the Harness crashing.

When the Harness-owned final verifier fails, it appends a short public feedback
message to the next model turn and permits at most AGENT_MAX_RETRIES repairs.
This feedback is a verifier observation, not private model reasoning.

## Deliberate limitation

The original Phase-2 task set recognized pytest commands only. Phase 3 adds one
equally narrow Java family for a real benchmark: offline Maven module tests of
the form `mvn -o -pl <module> -Dtest=<TestClass> test`. General compilation/test
classification remains deferred.
