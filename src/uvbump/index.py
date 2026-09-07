"""Asking a package index for the versions of a project.

Uses the PEP 691 JSON simple API, so any index that speaks it works: PyPI by
default, or a mirror, a proxy, or a private index through --index-url.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from .deps import canonical_name
from .versions import Version, parse, sorted_versions

DEFAULT_INDEX = "https://pypi.org/simple"
ACCEPT = "application/vnd.pypi.simple.v1+json"

# A resolver takes a project name and returns its latest usable version, or None.
Resolver = Callable[[str], "Version | None"]


class IndexUnavailable(RuntimeError):
    """The index could not be reached or did not answer with JSON."""


def version_of_filename(filename: str, prefix: str) -> str | None:
    """The version a distribution file name carries, or None if it is not ours."""
    stem = filename
    for suffix in (".whl", ".tar.gz", ".zip", ".tar.bz2", ".egg"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        return None
    # A project name may hold hyphens, so try every split point and keep the one
    # whose left side normalises to the project we asked for.
    for cut, char in enumerate(stem):
        if char != "-" or canonical_name(stem[:cut]) != prefix:
            continue
        rest = stem[cut + 1 :]
        # A wheel carries build tags after the version; a source archive does not.
        return rest.split("-", 1)[0] if filename.endswith(".whl") else rest
    return None


def versions_from_filenames(filenames: Iterable[str], name: str) -> list[str]:
    """Older indexes do not advertise a `versions` key. Read the file names instead."""
    prefix = canonical_name(name)
    found = {v for v in (version_of_filename(f, prefix) for f in filenames) if v}
    return [str(version) for version in sorted_versions(found)]


def yanked_versions(files: Iterable[dict], name: str) -> set[str]:
    """Versions whose every file has been yanked. uv and pip skip those, so do we."""
    prefix = canonical_name(name)
    seen: set[str] = set()
    live: set[str] = set()
    for entry in files:
        version = version_of_filename(entry.get("filename", ""), prefix)
        if version is None:
            continue
        seen.add(version)
        if not entry.get("yanked"):  # False, or a string giving the reason.
            live.add(version)
    return seen - live


def fetch_versions(name: str, index_url: str = DEFAULT_INDEX, timeout: float = 15.0) -> list[str]:
    url = f"{index_url.rstrip('/')}/{canonical_name(name)}/"
    request = urllib.request.Request(url, headers={"Accept": ACCEPT, "User-Agent": "uvbump"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise IndexUnavailable(f"{url}: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise IndexUnavailable(f"{url}: {error}") from error
    files = payload.get("files", [])
    versions = payload.get("versions")
    if versions is None:
        versions = versions_from_filenames([f.get("filename", "") for f in files], name)
    # A file name spells a version its own way, so compare on parsed versions.
    withdrawn = {v.key for v in (parse(t) for t in yanked_versions(files, name)) if v}
    return [v for v in versions if (p := parse(v)) is None or p.key not in withdrawn]


def make_resolver(
    index_url: str = DEFAULT_INDEX,
    *,
    allow_prereleases: bool = False,
    timeout: float = 15.0,
) -> Resolver:
    cache: dict[str, Version | None] = {}

    def resolve(name: str) -> Version | None:
        key = canonical_name(name)
        if key not in cache:
            cache[key] = latest_of(fetch_versions(name, index_url, timeout), allow_prereleases)
        return cache[key]

    return resolve


def latest_of(texts: Iterable[str], allow_prereleases: bool = False) -> Version | None:
    versions = sorted_versions(texts)
    if not allow_prereleases:
        stable = [v for v in versions if not v.is_prerelease]
        if stable:
            return stable[-1]
    return versions[-1] if versions else None


def resolve_all(names: Iterable[str], resolver: Resolver, workers: int = 8) -> dict[str, object]:
    """Resolve many names at once. A failure is stored as the exception, not raised."""
    unique = list(dict.fromkeys(canonical_name(name) for name in names))
    results: dict[str, object] = {}

    def one(name: str):
        try:
            return resolver(name)
        except IndexUnavailable as error:
            return error

    if not unique:
        return results
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(unique)))) as pool:
        for name, outcome in zip(unique, pool.map(one, unique)):
            results[name] = outcome
    return results
