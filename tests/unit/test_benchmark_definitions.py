"""Task regressions guard reference edits and separation of evaluation answers."""

from __future__ import annotations

import pytest

from codepilot.benchmarks.definitions import task_definitions
from codepilot.benchmarks.prepare import prepare_suite


def definition(task_id):
    return next(task for task in task_definitions() if task.task_id == task_id)


def load_source(task, fixed=False):
    namespace = {}
    content = task.reference_source() if fixed else task.files[task.fix_path]
    exec(compile(content, task.fix_path, "exec"), namespace)  # noqa: S102 -- owned fixture code
    return namespace


def test_recursive_redaction_reference_covers_nested_arrays_without_mutation():
    task = definition("audit-nested-redaction")
    payload = [[{"Token": "private", "items": [False, {"password": "private"}]}]]
    assert load_source(task)["redact"](payload) == payload
    assert load_source(task, fixed=True)["redact"](payload) == [[{
        "Token": "[REDACTED]", "items": [False, {"password": "[REDACTED]"}]
    }]]
    assert payload[0][0]["Token"] == "private"


def test_query_reference_preserves_values_blanks_and_decoding():
    task = definition("query-repeated-values")
    query = "tag=&tag=a+b&tag=c%2Bd"
    assert load_source(task)["query_values"](query) == {"tag": ["c+d"]}
    assert load_source(task, fixed=True)["query_values"](query) == {"tag": ["", "a b", "c+d"]}


def test_prepare_is_idempotent_and_keeps_answers_outside_repos(tmp_path):
    first = prepare_suite(tmp_path / "benchmarks")
    second = prepare_suite(tmp_path / "benchmarks")
    assert first == second
    assert first["task_count"] == 10
    for task in task_definitions():
        repo = tmp_path / "benchmarks" / "repos" / task.task_id
        assert not (repo / "acceptance").exists()
        assert not (repo / "reference").exists()
        assert not any("acceptance" in path.name for path in repo.rglob("*.py"))


def test_prepare_refuses_to_overwrite_user_changes(tmp_path):
    output = tmp_path / "benchmarks"
    prepare_suite(output)
    source_path = output / "repos" / "addition-smoke" / "calculator.py"
    source_path.write_text("# user work must survive\n", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        prepare_suite(output)
    assert source_path.read_text(encoding="utf-8") == "# user work must survive\n"
