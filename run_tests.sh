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

# Ensure auxiliary packages
pip show aiomysql >/dev/null 2>&1 || pip install aiomysql || true
pip show xmlrunner >/dev/null 2>&1 || pip install xmlrunner || true

# Prepare environment
LOG_DIR="${LOG_DIR:-$(pwd)/logs}"
export LOG_DIR
mkdir -p "$LOG_DIR"
mkdir -p test-results

# Run tests with JUnit XML output
set +e
echo "🧪 Running all test scripts in tests/ directory..."
python3 -m xmlrunner discover -s tests -p "test_*.py" -o test-results
TEST_EXIT_CODE=$?
set -e

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "❌ Tests failed."
else
    echo "✅ All tests passed."
fi

# Deactivate venv
echo "🔒 Deactivating the virtual environment..."
deactivate

exit $TEST_EXIT_CODE
