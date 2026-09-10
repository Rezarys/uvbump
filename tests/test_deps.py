import unittest

from uvbump.deps import apply, collect, load, parse_requirement, plan
from uvbump.versions import Version

DOCUMENT = """\
[project]
name = "demo"
version = "0.1.0"
# Runtime dependencies. Keep this comment.
dependencies = [
    "requests>=2.28",          # HTTP, pinned low on purpose
    "click>=8.0,<9",
    "attrs~=23.1",
    "typing-extensions",
    "packaging @ https://example.invalid/packaging.whl",
    'rich==13.0.0',
]

[project.optional-dependencies]
docs = ["sphinx>=7.0"]

[dependency-groups]
dev = ["pytest>=8.0", { include-group = "docs" }]

[tool.uv]
dev-dependencies = ["ruff>=0.4"]
constraint-dependencies = ["urllib3>=2.0"]
override-dependencies = ["werkzeug>=3.0"]
"""

LATEST = {
    "requests": "2.32.5",
    "click": "8.1.7",
    "attrs": "23.2.0",
    "typing-extensions": "4.12.0",
    "rich": "14.0.0",
    "sphinx": "8.1.0",
    "pytest": "8.3.0",
    "ruff": "0.6.0",
    "urllib3": "2.2.3",
    "werkzeug": "3.1.3",
}


def latest(name):
    text = LATEST.get(name.replace("_", "-").lower())
    return Version(text) if text else None


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.requirements = collect(load(DOCUMENT))
        self.by_name = {r.name: r for r in self.requirements}

    def test_reads_the_six_tables(self):
        self.assertEqual(
            sorted(self.by_name),
            [
                "attrs",
                "click",
                "pytest",
                "requests",
                "rich",
                "ruff",
                "sphinx",
                "typing-extensions",
                "urllib3",
                "werkzeug",
            ],
        )

    def test_records_the_table_each_entry_came_from(self):
        self.assertEqual(self.by_name["sphinx"].table, "project.optional-dependencies.docs")
        self.assertEqual(self.by_name["pytest"].table, "dependency-groups.dev")
        self.assertEqual(self.by_name["ruff"].table, "tool.uv.dev-dependencies")
        self.assertEqual(self.by_name["urllib3"].table, "tool.uv.constraint-dependencies")
        self.assertEqual(self.by_name["werkzeug"].table, "tool.uv.override-dependencies")

    def test_ignores_direct_url_references_and_include_group(self):
        self.assertNotIn("packaging", self.by_name)

    def test_isolates_the_specifier_span(self):
        self.assertEqual(self.by_name["click"].spec_text, ">=8.0,<9")
        self.assertEqual(self.by_name["typing-extensions"].spec_text, "")

    def test_keeps_extras_and_markers_out_of_the_span(self):
        requirement = parse_requirement('uvicorn[standard] >= 0.30 ; python_version >= "3.9"', "t")
        self.assertEqual(requirement.name, "uvicorn")
        self.assertEqual(requirement.spec_text, ">= 0.30")
        self.assertEqual(
            requirement.with_spec(">=0.32"), 'uvicorn[standard] >=0.32 ; python_version >= "3.9"'
        )


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.by_name = {r.name: r for r in collect(load(DOCUMENT))}

    def plan_for(self, name, **kwargs):
        return plan(self.by_name[name], latest(name), **kwargs)

    def test_bumps_a_lower_bound_to_the_full_latest(self):
        self.assertEqual(self.plan_for("requests").new_spec, ">=2.32.5")

    def test_keeps_the_precision_of_a_compatible_release_clause(self):
        self.assertEqual(self.plan_for("attrs").new_spec, "~=23.2")

    def test_moves_a_pin(self):
        self.assertEqual(self.plan_for("rich").new_spec, "==14.0.0")

    def test_keeps_an_upper_bound_that_still_holds(self):
        self.assertEqual(self.plan_for("click").new_spec, ">=8.1.7,<9")

    def test_skips_a_dependency_held_back_by_its_upper_bound(self):
        requirement = parse_requirement("click>=8.0,<8.1", "t")
        change = plan(requirement, Version("8.1.7"))
        self.assertFalse(change.bumped)
        self.assertIn("held back by the upper bound <8.1", change.reason)

    def test_widen_raises_the_upper_bound(self):
        requirement = parse_requirement("click>=8.0,<8.1", "t")
        self.assertEqual(plan(requirement, Version("8.1.7"), widen=True).new_spec, ">=8.1.7,<9.0")

    def test_skips_an_unbounded_dependency(self):
        change = self.plan_for("typing-extensions")
        self.assertFalse(change.bumped)
        self.assertEqual(change.reason, "no version bound to update")

    def test_up_to_date_is_neither_a_bump_nor_a_complaint(self):
        change = plan(parse_requirement("requests>=2.32.5", "t"), Version("2.32.5"))
        self.assertFalse(change.bumped)
        self.assertIsNone(change.reason)

    def test_missing_from_the_index(self):
        change = plan(parse_requirement("ghost>=1.0", "t"), None)
        self.assertEqual(change.reason, "not found on the index")

    def test_prefix_pin_keeps_its_shape(self):
        self.assertEqual(plan(parse_requirement("django==4.2.*", "t"), Version("5.1.3")).new_spec,
                         "==5.1.*")

    def test_leaves_arbitrary_equality_alone(self):
        change = plan(parse_requirement("odd===1.0-weird", "t"), Version("2.0"))
        self.assertFalse(change.bumped)

    def test_never_goes_backwards(self):
        change = plan(parse_requirement("requests>=3.0", "t"), Version("2.32.5"))
        self.assertFalse(change.bumped)

    def test_a_prefix_pin_never_goes_backwards_either(self):
        # An index that is behind, a mirror, or a bound written ahead on purpose.
        change = plan(parse_requirement("django==4.2.*", "t"), Version("3.9.1"))
        self.assertFalse(change.bumped)

    def test_two_bounds_to_move_are_left_alone(self):
        change = plan(parse_requirement("odd>=1.0,==2.0", "t"), Version("3.0"))
        self.assertFalse(change.bumped)
        self.assertIn("two bounds to move", change.reason)


class TestApply(unittest.TestCase):
    def test_rewrites_in_place_and_keeps_everything_else(self):
        requirements = collect(load(DOCUMENT))
        changes = [c for c in (plan(r, latest(r.name)) for r in requirements) if c.bumped]
        result = apply(DOCUMENT, changes)

        self.assertIn('"requests>=2.32.5",          # HTTP, pinned low on purpose', result)
        self.assertIn("# Runtime dependencies. Keep this comment.", result)
        self.assertIn("'rich==14.0.0'", result)  # Single quotes survive.
        self.assertIn('"packaging @ https://example.invalid/packaging.whl"', result)
        self.assertIn('docs = ["sphinx>=8.1.0"]', result)
        self.assertIn('dev-dependencies = ["ruff>=0.6.0"]', result)
        self.assertIn('constraint-dependencies = ["urllib3>=2.2.3"]', result)
        self.assertIn('override-dependencies = ["werkzeug>=3.1.3"]', result)
        self.assertIn('{ include-group = "docs" }', result)
        self.assertEqual(len(result.splitlines()), len(DOCUMENT.splitlines()))

    def test_a_second_pass_finds_nothing_left_to_do(self):
        requirements = collect(load(DOCUMENT))
        changes = [c for c in (plan(r, latest(r.name)) for r in requirements) if c.bumped]
        once = apply(DOCUMENT, changes)
        again = [c for c in (plan(r, latest(r.name)) for r in collect(load(once))) if c.bumped]
        self.assertEqual(again, [])

    def test_writing_nothing_is_a_no_op(self):
        self.assertEqual(apply(DOCUMENT, []), DOCUMENT)


if __name__ == "__main__":
    unittest.main()
