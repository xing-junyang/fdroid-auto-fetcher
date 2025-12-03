#!/bin/bash
#
# F-Droid Auto-Builder - Quick Setup Script
#

set -e

echo "=== F-Droid Auto-Builder Setup ==="
echo ""

# Check Python
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "ERROR: Python not found. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Found Python: $PYTHON_VERSION"

# Check Git
echo "Checking Git installation..."
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version | awk '{print $3}')
    echo "Found Git: $GIT_VERSION"
else
    echo "ERROR: Git not found. Please install Git 2.30 or higher."
    exit 1
fi

# Check Java
echo "Checking Java installation..."
if command -v java &> /dev/null; then
    JAVA_VERSION=$(java -version 2>&1 | head -n 1)
    echo "Found Java: $JAVA_VERSION"
else
    echo "WARNING: Java not found. Install Java JDK 8, 11, or 17 for building apps."
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
$PYTHON_CMD -m pip install --upgrade pip
$PYTHON_CMD -m pip install -r requirements.txt

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit config.ini to configure your workspace path"
echo "2. Run the service: $PYTHON_CMD main.py"
echo ""
echo "For more information, see README.md"
