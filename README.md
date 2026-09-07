# uvbump

Upgrades the version bounds declared in your `pyproject.toml`, in place, without touching your comments or your formatting. For anyone whose `pyproject.toml` still says `requests>=2.28` while the lock file has been on 2.32.5 for a year.

```
uvx --from git+https://github.com/Rezarys/uvbump uvbump
```

Not on PyPI yet, so that is the install line for now. See [Install](#install).

`uv lock` and `uv sync --upgrade` move your lock file. They leave the bounds you wrote in `pyproject.toml` exactly where they were, so a project can sit on `requests>=2.28` for two years while actually running 2.32.5. The usual fix is a `uv remove` then `uv add` cycle, which rewrites the file and drops every comment in it. uvbump edits the bound and nothing else.

```console
$ uvbump
  requests           >=2.28 -> >=2.32.5
  click              >=8.0,<9 -> >=8.1.7,<9
  attrs              ~=23.1 -> ~=23.2
  rich               ==13.0.0 -> ==14.0.0
  typing-extensions  skipped: no version bound to update
pyproject.toml: 4 bound(s) updated
uv.lock updated
```

The diff is one line per bound. Comments, key order, quoting style and blank lines come back byte for byte.

## What it reads

Every dependency table that uv understands, not just the first one:

- `project.dependencies`
- `project.optional-dependencies.*`
- `dependency-groups.*`
- `tool.uv.dev-dependencies`
- `tool.uv.constraint-dependencies`

## What it writes

- `requests>=2.28`, latest 2.32.5, becomes `requests>=2.32.5`.
- `rich==13.0.0`, latest 14.0.0, becomes `rich==14.0.0`.
- `attrs~=23.1`, latest 23.2.0, becomes `attrs~=23.2`, kept at the same precision so the ceiling still means something.
- `django==4.2.*`, latest 5.1.3, becomes `django==5.1.*`.
- `click>=8.0,<9`, latest 8.1.7, becomes `click>=8.1.7,<9`.
- `click>=8.0,<8.1`, latest 8.1.7, is left alone, and uvbump tells you the upper bound is what held it back.
- `typing-extensions` with no bound is left alone, there is nothing to move.
- `pkg @ https://...` is left alone, direct references are never touched.

It never moves a bound backwards, and it never invents a bound you did not write. A version whose every file has been yanked is not a candidate, the same way uv and pip pass over it. Pass `--widen` if you do want the upper bound raised to the next major instead of being skipped.

## Limits

Worth knowing before you run it:

- It is not on PyPI yet.
- It reads the index, not your environment. It offers the latest release, without checking that release against your `requires-python` or against what your other dependencies allow. `uv lock` is what tells you whether the set still resolves, which is why uvbump runs it for you unless you pass `--no-lock`.
- A requirement with two bounds to move, such as `pkg>=1.0,==2.0`, is left alone rather than guessed at.
- A dependency with no bound at all stays without one. uvbump moves bounds, it does not add them.
- Markers, extras and direct URL references are carried through untouched, never interpreted.
- It edits `pyproject.toml` only. Your `requirements.txt` files are not its business.

## In CI

```yaml
- run: uvx --from git+https://github.com/Rezarys/uvbump uvbump --check
```

`--check` writes nothing and exits 1 when a declared bound is behind the index, so a job can fail on a stale `pyproject.toml` the same way it fails on unformatted code. Exit 0 means every bound is current, exit 2 means uvbump could not do its job.

## Options

```
uvbump [PATH] [options]

  PATH               pyproject.toml, or the directory holding it (default: ./pyproject.toml)
  --check            write nothing, exit 1 when a bound is behind the index
  -n, --dry-run      show what would change, write nothing, exit 0
  --only NAME        only this dependency, repeatable
  --exclude NAME     never this dependency, repeatable
  --group TABLE      only tables whose name contains this, repeatable (for example: --group dev)
  --widen            raise an upper bound that holds a dependency back, instead of skipping it
  --pre              consider pre-releases
  --index-url URL    PEP 691 simple index (default: $UV_INDEX_URL, then $PIP_INDEX_URL, else PyPI)
  --no-lock          do not run `uv lock` after writing
  --quiet            only print what changed
```

Examples:

```console
# Two packages, nothing else.
$ uvbump --only requests --only httpx

# Dev tables only, and leave the lock file alone.
$ uvbump --group dev --no-lock

# Look first.
$ uvbump --dry-run

# A mirror or a private index.
$ uvbump --index-url https://my.index/simple
```

## Install

uvbump is not on PyPI yet. Today you install it from this repository, which pins you to a commit you can read:

```console
$ uvx --from git+https://github.com/Rezarys/uvbump uvbump
$ pip install git+https://github.com/Rezarys/uvbump@v0.1.0
```

Once it is on PyPI, `uvx uvbump` and `pip install uvbump==0.1.0` will work, and this section will say so.

uvbump needs Python 3.11 or later and has no dependencies. It asks your index over the PEP 691 JSON API, which means a mirror or a private index works too. It sends nothing anywhere else and collects nothing.

## Why the bounds matter

If you publish a library, the bounds in `pyproject.toml` are the contract your users resolve against, and a lock file does not reach them. If you ship an application, stale lower bounds quietly widen the set of resolutions your CI has never tried. Either way the file is the thing that has to be current, and it is the one thing no tool was updating.

## Tests

```console
$ python3 run_tests.py
```

No test dependencies either.

## Prior art

`uv` itself does not do this yet, and the request is one of the most upvoted on its tracker: [astral-sh/uv#6794](https://github.com/astral-sh/uv/issues/6794) and [astral-sh/uv#1419](https://github.com/astral-sh/uv/issues/1419). Several people in those threads have published their own take, and they are worth a look if uvbump is not the shape you want. If uv ships this natively, uvbump has done its job and you should use uv.

Not affiliated with Astral or with the uv project.

## License

MIT.
