"""The `uvbump` command line."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .deps import Change, RewriteError, apply, canonical_name, collect, load, plan
from .index import DEFAULT_INDEX, IndexUnavailable, Resolver, make_resolver, resolve_all

EXIT_OK = 0
EXIT_OUTDATED = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uvbump",
        description=(
            "Upgrade the version bounds declared in pyproject.toml, in place, "
            "without touching comments or formatting."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="pyproject.toml",
        help="path to pyproject.toml, or to the directory holding it (default: ./pyproject.toml)",
    )
    parser.add_argument("--version", action="version", version=f"uvbump {__version__}")
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing and exit 1 when a bound can be moved forward (for CI)",
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="show what would change and write nothing"
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME",
        help="only this dependency, repeatable",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME",
        help="never this dependency, repeatable",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="TABLE",
        help="only tables whose name contains this, repeatable (for example: dev)",
    )
    parser.add_argument(
        "--widen",
        action="store_true",
        help="raise an upper bound that holds a dependency back, instead of skipping it",
    )
    parser.add_argument("--pre", action="store_true", help="consider pre-releases")
    parser.add_argument(
        "--index-url",
        default=os.environ.get("UV_INDEX_URL", os.environ.get("PIP_INDEX_URL", DEFAULT_INDEX)),
        help=(
            "PEP 691 simple index "
            f"(default: $UV_INDEX_URL, then $PIP_INDEX_URL, else {DEFAULT_INDEX})"
        ),
    )
    parser.add_argument(
        "--no-lock", action="store_true", help="do not run `uv lock` after writing"
    )
    parser.add_argument("--quiet", action="store_true", help="only print what changed")
    return parser


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_dir():
        path = path / "pyproject.toml"
    return path


def wanted(change_name: str, table: str, args: argparse.Namespace) -> bool:
    name = canonical_name(change_name)
    if args.only and name not in {canonical_name(o) for o in args.only}:
        return False
    if name in {canonical_name(e) for e in args.exclude}:
        return False
    if args.group and not any(g.lower() in table.lower() for g in args.group):
        return False
    return True


def compute(text: str, args: argparse.Namespace, resolver: Resolver) -> list[Change]:
    document = load(text)
    requirements = [r for r in collect(document) if wanted(r.name, r.table, args)]
    latest = resolve_all((r.name for r in requirements), resolver)
    changes = []
    for requirement in requirements:
        found = latest.get(requirement.canonical)
        if isinstance(found, IndexUnavailable):
            changes.append(Change(requirement, None, None, str(found)))
            continue
        changes.append(plan(requirement, found, widen=args.widen))
    return changes


def report(changes: list[Change], out, quiet: bool) -> None:
    width = max((len(c.requirement.name) for c in changes), default=0)
    for change in changes:
        name = change.requirement.name.ljust(width)
        if change.bumped:
            old = change.requirement.spec_text or "(unbounded)"
            print(f"  {name}  {old} -> {change.new_spec}", file=out)
        elif change.reason and not quiet:
            print(f"  {name}  skipped: {change.reason}", file=out)


def run_lock(path: Path, out) -> None:
    if shutil.which("uv") is None:
        print("uv is not on PATH, skipping `uv lock`", file=out)
        return
    result = subprocess.run(
        ["uv", "lock"], cwd=path.parent or Path("."), capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"`uv lock` failed:\n{result.stderr.strip()}", file=out)
    else:
        print("uv.lock updated", file=out)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = sys.stderr if args.check else sys.stdout
    path = resolve_path(args.path)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return EXIT_ERROR

    text = path.read_text(encoding="utf-8")
    resolver = make_resolver(args.index_url, allow_prereleases=args.pre)
    try:
        changes = compute(text, args, resolver)
    except (ValueError, OSError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        return EXIT_ERROR

    bumped = [c for c in changes if c.bumped]
    report(changes, out, args.quiet)

    if not bumped:
        if not args.quiet:
            print("every bound is up to date", file=out)
        return EXIT_OK

    if args.check:
        print(f"{len(bumped)} bound(s) behind the index", file=out)
        return EXIT_OUTDATED
    if args.dry_run:
        print(f"{len(bumped)} bound(s) would change, nothing written", file=out)
        return EXIT_OK

    try:
        path.write_text(apply(text, bumped), encoding="utf-8")
    except RewriteError as error:
        print(f"{path}: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(f"{path}: {len(bumped)} bound(s) updated", file=out)
    if not args.no_lock:
        run_lock(path, out)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
