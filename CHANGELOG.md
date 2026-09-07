# Changelog

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
