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

# Prepare environment
LOG_DIR="${LOG_DIR:-$(pwd)/logs}"
export LOG_DIR
mkdir -p "$LOG_DIR"
mkdir -p test-results

# Run tests and generate minimal JUnit report
set +e
echo "🧪 Running all test scripts in tests/ directory..."
python3 <<'PY'
import glob, os, subprocess, sys, xml.etree.ElementTree as ET

tests = sorted(glob.glob("tests/test_*.py"))
suite = ET.Element("testsuite", name="tests", tests=str(len(tests)))
failures = 0

for path in tests:
    case = ET.SubElement(suite, "testcase", name=os.path.basename(path))
    proc = subprocess.run([sys.executable, path], capture_output=True, text=True)
    if proc.returncode != 0:
        failures += 1
        failure = ET.SubElement(case, "failure", message="non-zero exit")
        failure.text = proc.stdout + proc.stderr
    else:
        stdout = ET.SubElement(case, "system-out")
        stdout.text = proc.stdout

suite.set("failures", str(failures))
root = ET.Element("testsuites")
root.append(suite)
os.makedirs("test-results", exist_ok=True)
ET.ElementTree(root).write("test-results/results.xml", encoding="utf-8")
sys.exit(failures)
PY
TEST_EXIT_CODE=$?
set -e

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "❌ Some tests failed."
else
    echo "✅ All tests passed."
fi

# Deactivate venv
echo "🔒 Deactivating the virtual environment..."
deactivate

exit $TEST_EXIT_CODE
