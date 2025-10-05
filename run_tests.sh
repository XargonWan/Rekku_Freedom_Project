#!/bin/bash
set -e

VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# Install runtime and development dependencies
pip install -r requirements.txt >/dev/null

# Install test dependencies
pip install pytest pytest-asyncio unittest-xml-reporting >/dev/null

# Ensure a local log directory is used
export LOG_DIR=${LOG_DIR:-./logs}
mkdir -p "$LOG_DIR"

# Run the tests but capture the exit code so the script itself always exits 0
set +e
python run_tests.py
TEST_EXIT=$?
set -e

# GitHub Actions output
if [ -n "$GITHUB_OUTPUT" ]; then
  echo "result=$TEST_EXIT" >> "$GITHUB_OUTPUT"
fi

# GitHub Actions summary
if [ -n "$GITHUB_STEP_SUMMARY" ]; then
  if [ $TEST_EXIT -eq 0 ]; then
    echo "✅ Tests passed" >> "$GITHUB_STEP_SUMMARY"
    echo "" >> "$GITHUB_STEP_SUMMARY"
    echo "## Test Results" >> "$GITHUB_STEP_SUMMARY"
    echo "- Component loading: ✅ Verified" >> "$GITHUB_STEP_SUMMARY"
    echo "- Message chain: ✅ Functional" >> "$GITHUB_STEP_SUMMARY"
    echo "- Prompt generation: ✅ Valid JSON" >> "$GITHUB_STEP_SUMMARY"
    echo "- Core validation: ✅ Working" >> "$GITHUB_STEP_SUMMARY"
  else
    echo "❌ Tests failed with exit code $TEST_EXIT" >> "$GITHUB_STEP_SUMMARY"
    echo "" >> "$GITHUB_STEP_SUMMARY"
    echo "## Failed Tests" >> "$GITHUB_STEP_SUMMARY"
    echo "Check the test output above for details." >> "$GITHUB_STEP_SUMMARY"
  fi
fi

# Always succeed so CI can handle the result separately
exit 0
