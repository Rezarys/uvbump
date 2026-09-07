import io
import contextlib
import tempfile
import unittest
from pathlib import Path

from uvbump.cli import main
from uvbump.versions import Version

DOCUMENT = """\
[project]
name = "demo"
dependencies = [
    # keep me
    "requests>=2.28",
    "pytest>=8.0",
]
"""

LATEST = {"requests": "2.32.5", "pytest": "8.0"}


def fake_resolver(index_url=None, allow_prereleases=False, timeout=15.0):
    def resolve(name):
        text = LATEST.get(name.lower())
        return Version(text) if text else None

    return resolve


class CliCase(unittest.TestCase):
    def setUp(self):
        import uvbump.cli as cli

        self.real = cli.make_resolver
        cli.make_resolver = lambda index_url, allow_prereleases=False: fake_resolver()
        self.addCleanup(setattr, cli, "make_resolver", self.real)

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "pyproject.toml"
        self.path.write_text(DOCUMENT, encoding="utf-8")

    def run_cli(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(self.path), *argv])
        return code, stdout.getvalue() + stderr.getvalue()


class TestCli(CliCase):
    def test_writes_and_reports(self):
        code, output = self.run_cli("--no-lock")
        self.assertEqual(code, 0)
        self.assertIn(">=2.28 -> >=2.32.5", output)
        written = self.path.read_text(encoding="utf-8")
        self.assertIn('"requests>=2.32.5"', written)
        self.assertIn("# keep me", written)

    def test_check_writes_nothing_and_exits_one(self):
        code, output = self.run_cli("--check")
        self.assertEqual(code, 1)
        self.assertIn("1 bound(s) behind the index", output)
        self.assertEqual(self.path.read_text(encoding="utf-8"), DOCUMENT)

    def test_check_exits_zero_when_up_to_date(self):
        self.run_cli("--no-lock")
        code, _ = self.run_cli("--check")
        self.assertEqual(code, 0)

    def test_dry_run_writes_nothing_and_exits_zero(self):
        code, output = self.run_cli("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("nothing written", output)
        self.assertEqual(self.path.read_text(encoding="utf-8"), DOCUMENT)

    def test_exclude(self):
        code, output = self.run_cli("--exclude", "requests", "--no-lock")
        self.assertEqual(code, 0)
        self.assertNotIn("requests", output)
        self.assertEqual(self.path.read_text(encoding="utf-8"), DOCUMENT)

    def test_only(self):
        code, output = self.run_cli("--only", "requests", "--no-lock")
        self.assertEqual(code, 0)
        self.assertIn("requests", output)
        self.assertNotIn("pytest", output)

    def test_accepts_a_directory(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            code = main([str(self.path.parent), "--check"])
        self.assertEqual(code, 1)

    def test_missing_file_is_an_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main([str(self.path.parent / "nowhere" / "pyproject.toml")])
        self.assertEqual(code, 2)
        self.assertIn("no such file", stderr.getvalue())

    def test_broken_toml_is_an_error_not_a_traceback(self):
        self.path.write_text("[project\n", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main([str(self.path)])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
