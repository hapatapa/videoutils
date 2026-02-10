#!/bin/bash
set -e

# Define directories
VENV_DIR=".venv"

# 1. Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# 2. Upgrade pip inside the venv (optional but good practice)
"$VENV_DIR/bin/pip" install --upgrade pip

# 3. Install requirements inside the venv
if [ -f "requirements.txt" ]; then
    echo "Installing requirements..."
    "$VENV_DIR/bin/pip" install -r requirements.txt
else
    echo "requirements.txt not found!"
    exit 1
fi

# 4. Run the GUI application using the venv python
echo "Starting Video Compressor GUI..."
"$VENV_DIR/bin/python" gui.py
