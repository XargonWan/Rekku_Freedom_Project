#!/bin/bash
set -e

VENV_DIR=".venv"

# Create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "🌟 Creating the virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
echo "🔧 Activating the virtual environment..."
source "$VENV_DIR/bin/activate"

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt || true
else
    echo "⚠️ requirements.txt file not found. Make sure you have the necessary dependencies."
fi

# Ensure xmlrunner is available for JUnit XML output
pip install -q xmlrunner || true

# Prepare environment
LOG_DIR="${LOG_DIR:-$(pwd)/logs}"
export LOG_DIR
mkdir -p "$LOG_DIR"
mkdir -p test-results

# Run tests (prefer xmlrunner, fallback to minimal JUnit XML)
set +e
echo "🧪 Running tests..."
python3 <<'PY' 2>&1 | tee test-results/unit-tests.log
import glob, os, subprocess, sys, xml.etree.ElementTree as ET, pkgutil, unittest

if pkgutil.find_loader('xmlrunner'):
    import xmlrunner
    suite = unittest.defaultTestLoader.discover('tests')
    runner = xmlrunner.XMLTestRunner(output='test-results')
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
else:
    tests = sorted(glob.glob('tests/test_*.py'))
    suite_el = ET.Element('testsuite', name='tests', tests=str(len(tests)))
    failures = 0
    for path in tests:
        case = ET.SubElement(suite_el, 'testcase', name=os.path.basename(path))
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True)
        if proc.returncode != 0:
            failures += 1
            failure = ET.SubElement(case, 'failure', message='non-zero exit')
            failure.text = proc.stdout + proc.stderr
        else:
            stdout = ET.SubElement(case, 'system-out')
            stdout.text = proc.stdout
    suite_el.set('failures', str(failures))
    os.makedirs('test-results', exist_ok=True)
    ET.ElementTree(suite_el).write('test-results/results.xml', encoding='utf-8', xml_declaration=True)
    sys.exit(failures)
PY
TEST_EXIT_CODE=${PIPESTATUS[0]}
set -e

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "❌ Some tests failed."
else
    echo "✅ All tests passed."
fi

# If running inside GitHub Actions, publish a step summary
if [ -n "$GITHUB_STEP_SUMMARY" ]; then
    {
        echo "## Unit test results"
        echo ""
        if [ $TEST_EXIT_CODE -ne 0 ]; then
            echo "- ❌ Unit tests failed with exit code $TEST_EXIT_CODE"
        else
            echo "- ✅ Unit tests passed"
        fi
    } >> "$GITHUB_STEP_SUMMARY"
fi

# Deactivate venv
echo "🔒 Deactivating the virtual environment..."
deactivate

exit $TEST_EXIT_CODE
