import os
import sys
import unittest
import logging
from xml.etree.ElementTree import Element, SubElement, ElementTree


class RecordingTestResult(unittest.TextTestResult):
    """TestResult that records successes for JUnit reporting."""

    def startTestRun(self):  # pragma: no cover - simple container
        self.successes = []
        super().startTestRun()

    def addSuccess(self, test):  # pragma: no cover - simple container
        self.successes.append(test)
        super().addSuccess(test)


def _write_junit_xml(result: RecordingTestResult, output_path: str) -> None:
    testsuite = Element(
        "testsuite",
        name="unittest",
        tests=str(result.testsRun),
        failures=str(len(result.failures)),
        errors=str(len(result.errors)),
        skipped=str(len(result.skipped)),
    )

    def _add_testcase(test, category: str | None = None, message: str | None = None):
        case = SubElement(
            testsuite,
            "testcase",
            classname=test.__class__.__name__,
            name=str(test),
        )
        if category:
            node = SubElement(case, category)
            if message:
                node.text = message

    for test in result.successes:
        _add_testcase(test)
    for test, err in result.failures:
        _add_testcase(test, "failure", err)
    for test, err in result.errors:
        _add_testcase(test, "error", err)
    for test, reason in result.skipped:
        _add_testcase(test, "skipped", reason)

    ElementTree(testsuite).write(output_path, encoding="utf-8", xml_declaration=True)


def run_tests() -> RecordingTestResult:
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingTestResult)
    return runner.run(suite)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    result = run_tests()

    if os.getenv("GITHUB_ACTIONS", "false").lower() == "true":
        os.makedirs("test-results", exist_ok=True)
        _write_junit_xml(result, os.path.join("test-results", "unittest.xml"))

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

