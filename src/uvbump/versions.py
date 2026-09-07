"""A small PEP 440 version parser, comparator and specifier evaluator.

uvbump ships with no dependencies, so the parts of PEP 440 it needs live here.
The subset is the one that shows up in real `pyproject.toml` files: epochs,
release segments, pre-releases, post-releases, dev releases, local versions,
and the `== != <= >= < > ~= ===` operators including `==1.4.*` prefix matching.
"""

from __future__ import annotations

import re
from typing import Iterable

_VERSION_RE = re.compile(
    r"""
    ^\s*v?
    (?:(?P<epoch>[0-9]+)!)?
    (?P<release>[0-9]+(?:\.[0-9]+)*)
    (?:[-_.]?(?P<pre_l>a|b|c|rc|alpha|beta|pre|preview)[-_.]?(?P<pre_n>[0-9]+)?)?
    (?:-(?P<post_n1>[0-9]+)|[-_.]?(?:post|rev|r)[-_.]?(?P<post_n2>[0-9]+)?)?
    (?P<dev>[-_.]?dev[-_.]?(?P<dev_n>[0-9]+)?)?
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

_PRE_ALIASES = {"alpha": "a", "beta": "b", "c": "rc", "pre": "rc", "preview": "rc"}
_PRE_ORDER = {"a": 0, "b": 1, "rc": 2}

_INF = float("inf")


class InvalidVersion(ValueError):
    """Raised when a string is not a PEP 440 version."""


class Version:
    """A comparable PEP 440 version."""

    __slots__ = ("text", "epoch", "release", "pre", "post", "dev", "local")

    def __init__(self, text: str) -> None:
        match = _VERSION_RE.match(text)
        if match is None:
            raise InvalidVersion(text)
        self.text = text.strip()
        self.epoch = int(match.group("epoch") or 0)
        self.release = tuple(int(part) for part in match.group("release").split("."))
        pre_l = match.group("pre_l")
        if pre_l is None:
            self.pre = None
        else:
            letter = _PRE_ALIASES.get(pre_l.lower(), pre_l.lower())
            self.pre = (letter, int(match.group("pre_n") or 0))
        post = match.group("post_n1") or match.group("post_n2")
        self.post = int(post) if post is not None else None
        self.dev = int(match.group("dev_n") or 0) if match.group("dev") else None
        self.local = match.group("local")

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None or self.dev is not None

    @property
    def key(self) -> tuple:
        release = _strip_trailing_zeros(self.release)
        if self.pre is not None:
            pre = (_PRE_ORDER[self.pre[0]], self.pre[1])
        elif self.dev is not None and self.post is None:
            # A dev release with no pre-release sorts before every pre-release.
            pre = (-1, 0)
        else:
            pre = (_INF, 0)
        post = self.post if self.post is not None else -1
        dev = self.dev if self.dev is not None else _INF
        return (self.epoch, release, pre, post, dev)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Version) and self.key == other.key

    def __lt__(self, other: "Version") -> bool:
        return self.key < other.key

    def __le__(self, other: "Version") -> bool:
        return self.key <= other.key

    def __gt__(self, other: "Version") -> bool:
        return self.key > other.key

    def __ge__(self, other: "Version") -> bool:
        return self.key >= other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __repr__(self) -> str:
        return f"Version({self.text!r})"

    def __str__(self) -> str:
        return self.text


def _strip_trailing_zeros(release: tuple) -> tuple:
    parts = list(release)
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def parse(text: str) -> Version | None:
    """Parse a version, or return None when the string is not PEP 440."""
    try:
        return Version(text)
    except InvalidVersion:
        return None


def sorted_versions(texts: Iterable[str]) -> list[Version]:
    """Parse and sort version strings, dropping the ones that do not parse."""
    parsed = [v for v in (parse(t) for t in texts) if v is not None]
    return sorted(parsed)


_SPEC_RE = re.compile(r"^\s*(===|==|!=|~=|<=|>=|<|>)\s*([^\s,]+)\s*$")


class Specifier:
    """One clause of a version specifier set, such as `>=2.1` or `==1.4.*`."""

    __slots__ = ("operator", "version_text", "_prefix", "_version")

    def __init__(self, clause: str) -> None:
        match = _SPEC_RE.match(clause)
        if match is None:
            raise InvalidVersion(clause)
        self.operator, self.version_text = match.group(1), match.group(2)
        self._prefix = self.version_text.endswith(".*")
        base = self.version_text[:-2] if self._prefix else self.version_text
        self._version = None if self.operator == "===" else parse(base)
        if self._version is None and self.operator != "===":
            raise InvalidVersion(clause)

    def contains(self, candidate: Version) -> bool:
        if self.operator == "===":
            return candidate.text == self.version_text
        pinned = self._version
        assert pinned is not None
        if self._prefix:
            head = pinned.release
            matches = candidate.release[: len(head)] == head
            return matches if self.operator == "==" else not matches
        if self.operator == "==":
            return candidate == pinned
        if self.operator == "!=":
            return candidate != pinned
        if self.operator == "<=":
            return candidate <= pinned
        if self.operator == ">=":
            return candidate >= pinned
        if self.operator == "<":
            return candidate < pinned
        if self.operator == ">":
            return candidate > pinned
        if self.operator == "~=":
            if len(pinned.release) < 2:
                raise InvalidVersion(f"~={self.version_text}")
            ceiling = pinned.release[:-1]
            return candidate >= pinned and candidate.release[: len(ceiling)] == ceiling
        raise InvalidVersion(self.operator)

    def __str__(self) -> str:
        return f"{self.operator}{self.version_text}"


def parse_specifiers(text: str) -> list[Specifier]:
    """Parse a comma separated specifier set. An empty string gives an empty list."""
    clauses = [part for part in text.split(",") if part.strip()]
    return [Specifier(clause) for clause in clauses]


def satisfies(candidate: Version, specifiers: Iterable[Specifier]) -> bool:
    return all(spec.contains(candidate) for spec in specifiers)
