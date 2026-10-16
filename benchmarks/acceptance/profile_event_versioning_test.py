from copy import deepcopy
import pytest
from profiles.errors import ProjectionError
from profiles.projector import project_profile


def test_identical_duplicates_are_idempotent_and_input_is_unchanged():
    events = [
        {"version": 2, "changes": {"plan": "pro"}},
        {"version": 1, "changes": {"display_name": "Ada"}},
        {"version": 2, "changes": {"plan": "pro"}},
    ]
    original = deepcopy(events)
    assert project_profile(events) == {
        "version": 2, "display_name": "Ada", "plan": "pro"
    }
    assert events == original


def test_conflicts_and_gaps_are_rejected():
    with pytest.raises(ProjectionError):
        project_profile([
            {"version": 1, "changes": {"plan": "free"}},
            {"version": 1, "changes": {"plan": "pro"}},
        ])
    with pytest.raises(ProjectionError):
        project_profile([{"version": 2, "changes": {"plan": "pro"}}])


def test_empty_stream_has_zero_version():
    assert project_profile([]) == {"version": 0}
