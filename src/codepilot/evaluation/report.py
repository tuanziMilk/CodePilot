"""Render saved evaluation data without calling a model or rerunning a task."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _display(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# CodePilot evaluation",
        "",
        "| Config | Cases | Success | Test pass | Avg steps | Avg tokens | Avg latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in summary.get("by_config", {}).items():
        values = [
            name,
            metrics["runs"],
            metrics["success_rate"],
            metrics["test_pass_rate"],
            metrics.get("avg_steps"),
            metrics.get("avg_total_tokens"),
            metrics.get("avg_run_elapsed_ms"),
        ]
        lines.append("| " + " | ".join(_display(value) for value in values) + " |")
    lines += [
        "",
        "## Operational metrics",
        "",
        "| Config | Avg reads | Avg searches | Avg denied | Plan no-ops | Step-limit saves | Changed Hit@1 | Changed Hit@3 | Reference Hit@1 | Reference recall@K |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in summary.get("by_config", {}).items():
        operational = [
            name,
            metrics.get("avg_read_file_count"),
            metrics.get("avg_search_text_count"),
            metrics.get("avg_tool_denied_count"),
            metrics.get("plan_noops"),
            metrics.get("step_limit_successes"),
            metrics.get("retrieval_hit_at_1_rate"),
            metrics.get("retrieval_hit_at_3_rate"),
            metrics.get("retrieval_reference_hit_at_1_rate"),
            metrics.get("avg_retrieval_reference_file_recall"),
        ]
        lines.append("| " + " | ".join(_display(value) for value in operational) + " |")
    lines += [
        "",
        "## Context metrics",
        "",
        "| Config | Avg input tokens | Avg compactions | Avg total chars sent | Avg max canonical chars | Avg max sent chars | Avg chars saved |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in summary.get("by_config", {}).items():
        context = [
            name,
            metrics.get("avg_input_tokens"),
            metrics.get("avg_context_compaction_count"),
            metrics.get("avg_total_context_chars_sent"),
            metrics.get("avg_max_context_chars_before"),
            metrics.get("avg_max_context_chars_after"),
            metrics.get("avg_context_chars_saved"),
        ]
        lines.append("| " + " | ".join(_display(value) for value in context) + " |")
    lines += [
        "",
        "Success requires verified_success, external acceptance and allowed-file audit.",
        "Test pass measures external acceptance separately, including runs that failed to terminate.",
        "Missing measurements remain null/n/a; sample counts are in report.json.",
        "reliable/full bundle planning and reproduction. They do not isolate planning alone.",
        "Synthetic tasks and small sample sizes limit generalization; inspect trajectories and failures.",
        "",
    ]
    return "\n".join(lines)


def write_reports(summary: dict[str, Any], output: Path) -> None:
    (output / "report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    fields = [
        "task_id",
        "difficulty",
        "task_family",
        "config",
        "evaluation_outcome",
        "terminal_state",
        "acceptance_passed",
        "audit_passed",
        "steps",
        "retry_count",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "run_elapsed_ms",
        "llm_latency_ms",
        "tool_error_count",
        "tool_denied_count",
        "read_file_count",
        "search_text_count",
        "plan_noop_count",
        "context_compaction_count",
        "context_request_count",
        "total_context_chars_sent",
        "context_chars_saved",
        "max_context_chars_before",
        "max_context_chars_after",
        "max_context_messages_sent",
        "max_context_steps_compacted",
        "verified_at_step_limit",
        "retrieval_hit_rank",
        "retrieval_reference_hit_rank",
        "retrieval_reference_file_recall",
    ]
    with (output / "report.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in summary.get("records", []):
            row = {key: record.get(key) for key in fields}
            row["total_tokens"] = (record.get("token_usage") or {}).get("total_tokens")
            row["input_tokens"] = (record.get("token_usage") or {}).get("input_tokens")
            row["output_tokens"] = (record.get("token_usage") or {}).get("output_tokens")
            for key in (
                "run_elapsed_ms",
                "llm_latency_ms",
                "tool_error_count",
                "tool_denied_count",
                "read_file_count",
                "search_text_count",
                "plan_noop_count",
                "context_compaction_count",
                "context_request_count",
                "total_context_chars_sent",
                "context_chars_saved",
                "max_context_chars_before",
                "max_context_chars_after",
                "max_context_messages_sent",
                "max_context_steps_compacted",
            ):
                row[key] = (record.get("metrics") or {}).get(key)
            writer.writerow(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render saved CodePilot evaluation results.")
    parser.add_argument(
        "evaluation", type=Path, help="Evaluation directory or evaluation_summary.json"
    )
    args = parser.parse_args(argv)
    source = (
        args.evaluation / "evaluation_summary.json" if args.evaluation.is_dir() else args.evaluation
    )
    try:
        summary = json.loads(source.read_text(encoding="utf-8"))
        from codepilot.evaluation.runner import aggregate_records

        summary.update(aggregate_records(summary.get("records", [])))
        write_reports(summary, source.parent)
        print(render_markdown(summary))
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"Unable to read evaluation: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
