#!/usr/bin/env python3
"""Simple test runner for the project.

The script discovers tests under ``tests/`` using ``unittest``.  When running in
GitHub Actions it will attempt to produce a JUnit style XML report using
``unittest-xml-reporting`` (``xmlrunner``).  If the dependency is missing the
script falls back to the normal ``TextTestRunner`` while emitting a warning.
"""

from __future__ import annotations

import logging
import os
import sys
import unittest


def main() -> int:
    # Basic console logging so unexpected exceptions are visible.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
    except Exception:
        logging.exception("Failed to discover tests")
        return 1

    runner: unittest.TextTestRunner
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        try:
            import xmlrunner  # type: ignore

            os.makedirs("test-results", exist_ok=True)
            with open(os.path.join("test-results", "unittest.xml"), "wb") as output:
                runner = xmlrunner.XMLTestRunner(output=output, verbosity=2)
                result = runner.run(suite)
        except Exception as exc:  # pragma: no cover - exercised when xmlrunner missing
            logging.warning("xmlrunner not available: %s", exc)
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
    else:
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":  # pragma: no cover - manual execution
    try:
        sys.exit(main())
    except Exception:  # Catch any unexpected exception to ensure a proper exit code
        logging.exception("Unhandled exception during tests")
        sys.exit(1)
