#!/usr/bin/env bash
# One-time setup: creates a virtual environment and installs all dependencies.
# Run once, then activate the venv for subsequent commands:
#   source .venv/bin/activate

set -e

# ── Python version check ──────────────────────────────────────────────────────
python_cmd=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(sys.version_info[:2])')
        if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            python_cmd="$cmd"
            break
        fi
    fi
done

if [ -z "$python_cmd" ]; then
    echo "❌ Python 3.10+ is required. Please install it and re-run setup.sh"
    exit 1
fi

echo "✓ Using $($python_cmd --version)"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv/ ..."
    "$python_cmd" -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# ── Install dependencies ──────────────────────────────────────────────────────
echo "Installing dependencies ..."
.venv/bin/pip install --quiet --no-cache-dir --upgrade pip
.venv/bin/pip install --quiet --no-cache-dir -r requirements.txt
echo "✓ Dependencies installed"

# ── API key setup ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠  Created .env from .env.example"
    echo "   Edit .env and set your ANTHROPIC_API_KEY before running."
else
    echo "✓ .env already exists"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "Setup complete. Activate the environment and run:"
echo ""
echo "  source .venv/bin/activate"
echo "  python main.py \"Who invented the telephone?\""
echo ""
