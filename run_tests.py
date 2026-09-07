#!/usr/bin/env python3
"""Run the test suite with no dependencies and no installation:

    python3 run_tests.py

Equivalent to `python3 -m unittest discover -s tests` with `src` on the path.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

if __name__ == "__main__":
    tests = str(ROOT / "tests")
    suite = unittest.defaultTestLoader.discover(tests, top_level_dir=tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
