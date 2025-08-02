#!/bin/bash

# Name of the virtual environment directory
VENV_DIR=".venv"

# Check if the virtual environment already exists
if [ ! -d "$VENV_DIR" ]; then
    echo "🌟 Creating the virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate the virtual environment
echo "🔧 Activating the virtual environment..."
source "$VENV_DIR/bin/activate"

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
else
    echo "⚠️ requirements.txt file not found. Make sure you have the necessary dependencies."
fi

# Install aiomysql if not included in requirements.txt
echo "📦 Checking and installing aiomysql..."
pip show aiomysql > /dev/null 2>&1 || pip install aiomysql

# Run test scripts
echo "🧪 Running all test scripts in tests/ directory..."
python3 -m unittest discover -s tests -p "test_*.py"

# Check if tests were found and executed successfully
if [ $? -ne 0 ]; then
    echo "❌ Nessun test trovato o errore durante l'esecuzione dei test. Verifica la configurazione."
    deactivate
    exit 1
fi

# Deactivate the virtual environment
echo "🔒 Deactivating the virtual environment..."
deactivate