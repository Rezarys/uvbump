"""Reading the dependency tables of a `pyproject.toml`, and rewriting bounds in place.

Rewriting is done on the raw text, never by re-serialising the document, so
comments, key order, quoting style and blank lines survive untouched. That is
the whole point: the usual `remove` then `add` cycle loses them.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field

from .versions import Specifier, Version, parse, parse_specifiers

# PEP 508, restricted to what a dependency list holds: a name, optional extras,
# an optional specifier set, an optional marker.
_REQUIREMENT_RE = re.compile(
    r"""
    ^\s*
    (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)
    \s*(?P<extras>\[[^\]]*\])?
    \s*(?P<spec>[^;@]*)
    (?P<marker>;.*)?
    \s*$
    """,
    re.VERBOSE | re.DOTALL,
)

_ANCHOR_OPERATORS = ("~=", "==", ">=", ">")


def canonical_name(name: str) -> str:
    """PEP 503 normalised name."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class Requirement:
    """One entry of a dependency table."""

    raw: str
    name: str
    table: str
    spec_start: int
    spec_end: int
    specifiers: list[Specifier] = field(default_factory=list)

    @property
    def canonical(self) -> str:
        return canonical_name(self.name)

    @property
    def spec_text(self) -> str:
        return self.raw[self.spec_start : self.spec_end]

    def with_spec(self, spec_text: str) -> str:
        return self.raw[: self.spec_start] + spec_text + self.raw[self.spec_end :]


def parse_requirement(raw: str, table: str) -> Requirement | None:
    """Parse one dependency string. Returns None for anything uvbump will not touch:
    direct URL references, and entries that are not PEP 508 at all."""
    if "@" in raw.split(";", 1)[0]:
        return None
    match = _REQUIREMENT_RE.match(raw)
    if match is None:
        return None
    spec_raw = match.group("spec") or ""
    start, end = match.span("spec")
    stripped = spec_raw.strip()
    # Keep surrounding whitespace out of the replaced span.
    start += len(spec_raw) - len(spec_raw.lstrip())
    end -= len(spec_raw) - len(spec_raw.rstrip())
    if stripped.startswith("(") and stripped.endswith(")"):
        start += 1
        end -= 1
        stripped = stripped[1:-1]
    try:
        specifiers = parse_specifiers(stripped)
    except ValueError:
        return None
    return Requirement(
        raw=raw,
        name=match.group("name"),
        table=table,
        spec_start=start,
        spec_end=end,
        specifiers=specifiers,
    )


def _entries(value: object, table: str) -> list[Requirement]:
    found = []
    if not isinstance(value, list):
        return found
    for item in value:
        if not isinstance(item, str):
            continue  # `dependency-groups` may hold {include-group = "..."} tables.
        parsed = parse_requirement(item, table)
        if parsed is not None:
            found.append(parsed)
    return found


def collect(document: dict) -> list[Requirement]:
    """The requirements of the six tables uvbump reads: `project.dependencies`,
    `project.optional-dependencies`, `dependency-groups`, `tool.uv.dev-dependencies`,
    `tool.uv.constraint-dependencies` and `tool.uv.override-dependencies`."""
    found: list[Requirement] = []
    project = document.get("project")
    if isinstance(project, dict):
        found += _entries(project.get("dependencies"), "project.dependencies")
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for extra, value in optional.items():
                found += _entries(value, f"project.optional-dependencies.{extra}")
    groups = document.get("dependency-groups")
    if isinstance(groups, dict):
        for group, value in groups.items():
            found += _entries(value, f"dependency-groups.{group}")
    tool_uv = document.get("tool", {})
    if isinstance(tool_uv, dict):
        uv_table = tool_uv.get("uv")
        if isinstance(uv_table, dict):
            found += _entries(uv_table.get("dev-dependencies"), "tool.uv.dev-dependencies")
            constraints = uv_table.get("constraint-dependencies")
            found += _entries(constraints, "tool.uv.constraint-dependencies")
            overrides = uv_table.get("override-dependencies")
            found += _entries(overrides, "tool.uv.override-dependencies")
    return found


def load(text: str) -> dict:
    return tomllib.loads(text)


@dataclass
class Change:
    """What uvbump proposes for one requirement."""

    requirement: Requirement
    latest: Version | None
    new_spec: str | None
    reason: str | None = None

    @property
    def bumped(self) -> bool:
        return self.new_spec is not None

    @property
    def new_raw(self) -> str | None:
        return None if self.new_spec is None else self.requirement.with_spec(self.new_spec)


def _render(version: Version, components: int | None) -> str:
    if components is None:
        return version.text
    parts = list(version.release[:components])
    while len(parts) < components:
        parts.append(0)
    return ".".join(str(part) for part in parts)


def _next_bound(bound_text: str, latest: Version) -> str:
    """Raise an upper bound to the next major above `latest`, keeping its shape."""
    components = len(bound_text.split("."))
    parts = [latest.release[0] + 1] + [0] * (components - 1)
    return ".".join(str(part) for part in parts)


def plan(requirement: Requirement, latest: Version | None, *, widen: bool = False) -> Change:
    """Decide what to write for one requirement, or why nothing is written."""
    if latest is None:
        return Change(requirement, None, None, "not found on the index")
    if not requirement.specifiers:
        return Change(requirement, latest, None, "no version bound to update")

    anchors = [s for s in requirement.specifiers if s.operator in _ANCHOR_OPERATORS]
    if not anchors:
        return Change(requirement, latest, None, "no lower bound or pin to update")
    if len(anchors) > 1:
        clauses = " and ".join(str(a) for a in anchors)
        return Change(requirement, latest, None, f"two bounds to move ({clauses}), left alone")
    if any(s.operator == "===" for s in requirement.specifiers):
        return Change(requirement, latest, None, "arbitrary equality is left alone")
    anchor = anchors[0]
    is_prefix = anchor.version_text.endswith(".*")
    current = parse(anchor.version_text.removesuffix(".*"))
    if current is None:
        return Change(requirement, latest, None, "current bound is not PEP 440")
    if latest <= current:
        return Change(requirement, latest, None, None)

    components = None
    if anchor.operator == "~=" or is_prefix:
        components = len(anchor.version_text.removesuffix(".*").split("."))
    rendered = _render(latest, components)
    if is_prefix:
        rendered += ".*"
    if rendered == anchor.version_text:
        return Change(requirement, latest, None, None)

    clauses = []
    for spec in requirement.specifiers:
        if spec is anchor:
            clauses.append(f"{anchor.operator}{rendered}")
            continue
        if spec.contains(latest):
            clauses.append(str(spec))
            continue
        if spec.operator in ("<", "<=") and widen:
            clauses.append(f"{spec.operator}{_next_bound(spec.version_text, latest)}")
            continue
        held = "upper bound" if spec.operator in ("<", "<=") else "exclusion"
        return Change(
            requirement,
            latest,
            None,
            f"{latest} is held back by the {held} {spec}"
            + (" (use --widen)" if spec.operator in ("<", "<=") else ""),
        )
    return Change(requirement, latest, ",".join(clauses))


class RewriteError(RuntimeError):
    """The rewritten document did not come back the way it went in."""


def apply(text: str, changes: list[Change]) -> str:
    """Substitute each bumped requirement in the raw document text."""
    result = text
    for change in changes:
        if not change.bumped:
            continue
        raw, new_raw = change.requirement.raw, change.new_raw
        assert new_raw is not None
        replaced = False
        for quote in ('"', "'"):
            needle = f"{quote}{raw}{quote}"
            if needle in result:
                result = result.replace(needle, f"{quote}{new_raw}{quote}")
                replaced = True
        if not replaced:
            raise RewriteError(f"could not locate {raw!r} in the document")

    document = tomllib.loads(result)  # Raises on any TOML we broke.
    written = {req.raw for req in collect(document)}
    missing = [c.new_raw for c in changes if c.bumped and c.new_raw not in written]
    if missing:
        raise RewriteError(f"rewrite did not take effect for {missing}")
    return result
