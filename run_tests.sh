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

# Install dev dependencies if present (e.g., unittest-xml-reporting)
if [ -f "requirements-dev.txt" ]; then
    echo "📦 Installing dev dependencies..."
    pip install -r requirements-dev.txt || true
fi

# Prepare environment
LOG_DIR="$(pwd)/logs"
export LOG_DIR
mkdir -p "$LOG_DIR"
mkdir -p test-results

# Run tests
set +e
echo "🧪 Running tests..."
python run_tests.py 2>&1 | tee test-results/unit-tests.log
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
