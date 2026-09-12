# Changelog

## 0.2.0

- Reads `tool.uv.override-dependencies` as well, which brings the count to six tables. 0.1.0 read five, and the README wrongly said it read every table uv understands.
- Documents that `--check` exits 0 when a bound that is behind the index is held back by an upper bound or by a second anchor. That was already true in 0.1.0 and the README said the opposite.
- Published on PyPI under the distribution name `uv-pyproject-bump` (the `uvbump` name was taken by an unrelated project with the same normalized spelling). The command installed is still `uvbump`. The README no longer tells you to install from the git repository by default.

## 0.1.0

First release.

- Upgrades declared version bounds in `pyproject.toml` by editing the file text, so comments, key order, quoting style and blank lines are preserved.
- Reads `project.dependencies`, `project.optional-dependencies`, `dependency-groups`, `tool.uv.dev-dependencies` and `tool.uv.constraint-dependencies`.
- Handles `>=`, `>`, `==`, `~=` and `==X.Y.*` bounds, keeps a compatible release clause at its original precision, and refuses to move a bound backwards.
- Skips a dependency held back by an upper bound or an exclusion, and says which clause held it, unless `--widen`.
- Passes over a version whose every file has been yanked, and over a requirement carrying two bounds to move.
- `--check` for CI: writes nothing, exits 1 when a bound is behind the index.
- `--only`, `--exclude`, `--group`, `--dry-run`, `--pre`, `--index-url`, `--no-lock`, `--quiet`.
- Runs `uv lock` after writing when uv is on PATH.
- No dependencies. Python 3.11 or later.
