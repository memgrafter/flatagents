#!/bin/bash
set -e

cd "$(dirname "$0")"

# Setup virtualenv with build tools
if [ ! -d ~/virtualenvs/twine ]; then
    python -m venv ~/virtualenvs/twine
    ~/virtualenvs/twine/bin/pip install build twine
fi
source ~/virtualenvs/twine/bin/activate

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build
python -m build

# Upload to PyPI
twine upload dist/*

echo "Released $(ls dist/*.whl | head -1 | xargs basename)"
