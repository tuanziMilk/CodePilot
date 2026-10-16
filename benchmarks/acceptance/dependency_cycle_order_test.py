import pytest
from deploy.errors import DependencyCycleError
from deploy.planner import deployment_order


def test_shared_and_dependency_only_nodes_are_stable():
    graph = {"api": ["db", "cache"], "db": ["network"], "cache": ["network"]}
    original = {key: list(value) for key, value in graph.items()}
    assert deployment_order(graph, ["api"]) == ["network", "db", "cache", "api"]
    assert graph == original


def test_multiple_roots_are_not_duplicated():
    assert deployment_order({"web": ["core"], "worker": ["core"]},
                            ["web", "worker"]) == ["core", "web", "worker"]


def test_self_and_deep_cycles_raise():
    with pytest.raises(DependencyCycleError):
        deployment_order({"a": ["a"]}, ["a"])
    with pytest.raises(DependencyCycleError):
        deployment_order({"a": ["b"], "b": ["c"], "c": ["b"]}, ["a"])
