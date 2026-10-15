"""Deliberately conservative command authorization.

This is logical isolation only. It makes the Bash tool useful for bounded
inspection and test execution while rejecting command composition and mutation.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from codepilot.environment.workspace import Workspace

_MAVEN_MODULE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?:,[A-Za-z0-9_.-]+)*$")
_MAVEN_TEST_PATTERN = re.compile(r"^[A-Za-z0-9_.*,$-]+$")


class PermissionDenied(ValueError):
    """Raised when the Phase-1 command policy rejects a request."""


@dataclass(frozen=True)
class PermissionPolicy:
    version: str
    workspace: Workspace | None = None

    _FORBIDDEN_FRAGMENTS = (
        "rm ",
        "del ",
        "rmdir",
        "diskpart",
        "format",
        "shutdown",
        "reg ",
        "registry",
        "mkfs",
        "chmod",
        "chown",
        "curl ",
        "wget ",
    )
    _SHELL_OPERATORS = (";", "&", "|", ">", "<", "$", "`", "\n", "\r")
    _PROTECTED_FRAGMENTS = (
        ".git",
        ".codepilot",
        "hidden_tests",
        "verifier",
        "evaluation_metadata",
    )

    def authorize_command(self, command: str) -> None:
        normalized = command.strip()
        if not normalized:
            raise PermissionDenied("Empty commands are not allowed.")
        lowered = normalized.lower()
        if any(fragment in lowered for fragment in self._FORBIDDEN_FRAGMENTS):
            raise PermissionDenied("Command contains a forbidden destructive or network operation.")
        if any(fragment in lowered for fragment in self._PROTECTED_FRAGMENTS):
            raise PermissionDenied("Command refers to a protected workspace area.")
        if any(operator in normalized for operator in self._SHELL_OPERATORS):
            raise PermissionDenied("Shell composition and expansion are not allowed. Run one command at a time.")

        try:
            tokens = shlex.split(normalized, posix=True)
        except ValueError as error:
            raise PermissionDenied("Command could not be parsed safely.") from error
        if not tokens:
            raise PermissionDenied("Empty commands are not allowed.")

        executable = tokens[0]
        if tokens in (["pwd"], ["ls"], ["ls", "-l"]):
            return
        if executable == "rg":
            raise PermissionDenied("Use search_text: raw rg does not enforce Workspace protected paths.")
        if executable == "pytest" and self._is_bounded_pytest(tokens[1:]):
            return
        if executable == "git" and self._is_safe_git_inspection(tokens):
            return
        if (
            executable in {"python", "python3"}
            and tokens[1:3] == ["-m", "pytest"]
            and self._is_bounded_pytest(tokens[3:])
        ):
            return
        if executable == "mvn" and self._is_offline_maven_test(tokens):
            return
        raise PermissionDenied(
            "Command denied. Use file tools for paths/search, git diff/status, "
            "python -m pytest -q, or mvn -o -pl <module> -Dtest=<Class> test. "
            "Do not add shell operators, network options, output paths or skip-test flags."
        )

    def _is_bounded_pytest(self, arguments: list[str]) -> bool:
        safe_flags = {"-q", "-v", "-vv", "-x", "--disable-warnings", "--no-header", "--tb=short", "--tb=long"}
        for token in arguments:
            if token in safe_flags:
                continue
            # Git Bash expands brace/glob/tilde syntax after shlex parsing.
            # Only plain relative paths and pytest node separators are accepted.
            if token.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_./:-]+", token):
                return False
            target = token.split("::", 1)[0]
            parts = PurePosixPath(target.replace("\\", "/"))
            if (
                parts.is_absolute()
                or PureWindowsPath(target).drive
                or ".." in parts.parts
                or any(part.startswith(".") and part != "." for part in parts.parts)
            ):
                return False
            if self.workspace:
                try:
                    self.workspace.resolve(target)
                except ValueError:
                    return False
        return True

    @staticmethod
    def _is_safe_git_inspection(tokens: list[str]) -> bool:
        """Allow a small, explicit set of non-mutating Git checks."""

        if len(tokens) < 2:
            return False
        if tokens[1] == "status":
            return tokens[2:] in ([], ["--short"], ["--porcelain"])
        if tokens[1] != "diff":
            return False
        allowed_flags = {"--check", "--stat", "--name-only", "--no-ext-diff"}
        flags = tokens[2:]
        return len(flags) == len(set(flags)) and all(flag in allowed_flags for flag in flags)

    @staticmethod
    def _is_offline_maven_test(tokens: list[str]) -> bool:
        """Allow only a small, offline Maven test command family.

        Maven may otherwise resolve dependencies or run arbitrary lifecycle goals. The
        benchmark needs only module-scoped test execution with a named test class.
        """

        if len(tokens) < 2 or not ({"-o", "--offline"} & set(tokens)):
            return False

        test_goal_seen = False
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token == "test":
                if test_goal_seen:
                    return False
                test_goal_seen = True
                index += 1
                continue
            if token in {"-o", "--offline", "-q", "--quiet", "-am", "--also-make"}:
                index += 1
                continue
            if token in {"-pl", "--projects"}:
                if (
                    index + 1 >= len(tokens) - 1
                    or not _MAVEN_MODULE_PATTERN.fullmatch(tokens[index + 1])
                    or any(module in {".", ".."} for module in tokens[index + 1].split(","))
                ):
                    return False
                index += 2
                continue
            if token.startswith("-Dtest=") and _MAVEN_TEST_PATTERN.fullmatch(
                token.removeprefix("-Dtest=")
            ):
                index += 1
                continue
            return False
        return test_goal_seen
