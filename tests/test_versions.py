import unittest

from uvbump.index import latest_of, versions_from_filenames
from uvbump.versions import Specifier, Version, parse, parse_specifiers, sorted_versions


class TestVersion(unittest.TestCase):
    def test_orders_release_segments(self):
        self.assertLess(Version("1.9"), Version("1.10"))
        self.assertLess(Version("1.2.3"), Version("1.3"))
        self.assertEqual(Version("1.0"), Version("1.0.0"))

    def test_orders_pre_and_post_and_dev(self):
        order = ["1.0.dev1", "1.0a1", "1.0b2", "1.0rc1", "1.0", "1.0.post1", "1.1"]
        self.assertEqual([str(v) for v in sorted_versions(order)], order)

    def test_epoch_wins(self):
        self.assertLess(Version("1.0"), Version("1!0.1"))

    def test_aliases(self):
        self.assertEqual(Version("1.0alpha1"), Version("1.0a1"))
        self.assertEqual(Version("1.0-rc1"), Version("1.0c1"))

    def test_prerelease_flag(self):
        self.assertTrue(Version("2.0b1").is_prerelease)
        self.assertTrue(Version("2.0.dev3").is_prerelease)
        self.assertFalse(Version("2.0.post1").is_prerelease)

    def test_rejects_nonsense(self):
        self.assertIsNone(parse("not-a-version"))
        self.assertIsNone(parse(""))


class TestSpecifier(unittest.TestCase):
    def test_operators(self):
        cases = [
            (">=2.0", "2.1", True),
            (">=2.0", "1.9", False),
            ("<3", "2.9.9", True),
            ("<3", "3.0", False),
            ("!=1.5", "1.5", False),
            ("==1.4.2", "1.4.2", True),
            ("~=1.4", "1.9", True),
            ("~=1.4", "2.0", False),
            ("~=1.4.2", "1.4.9", True),
            ("~=1.4.2", "1.5.0", False),
            ("==1.4.*", "1.4.7", True),
            ("==1.4.*", "1.5.0", False),
            ("!=1.4.*", "1.5.0", True),
        ]
        for clause, candidate, expected in cases:
            with self.subTest(clause=clause, candidate=candidate):
                self.assertIs(Specifier(clause).contains(Version(candidate)), expected)

    def test_parses_a_set(self):
        specs = parse_specifiers(">=2.0,<3")
        self.assertEqual([str(s) for s in specs], [">=2.0", "<3"])
        self.assertEqual(parse_specifiers(""), [])


class TestLatest(unittest.TestCase):
    def test_skips_prereleases_by_default(self):
        available = ["1.0", "2.0b1"]
        self.assertEqual(str(latest_of(available)), "1.0")
        self.assertEqual(str(latest_of(available, allow_prereleases=True)), "2.0b1")

    def test_falls_back_to_a_prerelease_when_that_is_all_there_is(self):
        self.assertEqual(str(latest_of(["0.1a1"])), "0.1a1")

    def test_empty(self):
        self.assertIsNone(latest_of([]))

    def test_reads_versions_off_file_names(self):
        files = [
            "requests-2.32.5-py3-none-any.whl",
            "requests-2.32.5.tar.gz",
            "requests-2.31.0.tar.gz",
            "something-else-1.0.tar.gz",
            "requests-2.32.5.metadata",
        ]
        self.assertEqual(versions_from_filenames(files, "requests"), ["2.31.0", "2.32.5"])


if __name__ == "__main__":
    unittest.main()
