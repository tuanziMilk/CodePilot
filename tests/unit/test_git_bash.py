from pathlib import Path

from codepilot.environment.git_bash import GitBashEnvironment


def test_output_bounding_treats_missing_process_stream_as_empty_output(tmp_path: Path) -> None:
    bash_path = tmp_path / "bash.exe"
    bash_path.touch()
    environment = GitBashEnvironment(tmp_path, bash_path)

    assert environment._bound(None) == ""
