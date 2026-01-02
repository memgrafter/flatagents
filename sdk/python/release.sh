#!/bin/bash
set -e

cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"
ASSETS_DIR="$PWD/flatagents/assets"

echo "=== Python SDK Release Validation ==="
echo ""

# Extract versions from root TypeScript specs
echo "Extracting spec versions from TypeScript files..."
FLATAGENT_VERSION=$(npx tsx "$REPO_ROOT/scripts/generate-spec-assets.ts" --extract-version "$REPO_ROOT/flatagent.d.ts")
FLATMACHINE_VERSION=$(npx tsx "$REPO_ROOT/scripts/generate-spec-assets.ts" --extract-version "$REPO_ROOT/flatmachine.d.ts")

echo "TypeScript spec versions:"
echo "  flatagent.d.ts:   $FLATAGENT_VERSION"
echo "  flatmachine.d.ts: $FLATMACHINE_VERSION"
echo ""

# Extract versions from Python SDK
echo "Checking Python SDK versions..."
SDK_FLATAGENT_VERSION=$(grep -E '^\s*SPEC_VERSION\s*=\s*' flatagents/flatagent.py | grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' | tr -d '"')
SDK_FLATMACHINE_VERSION=$(grep -E '^\s*SPEC_VERSION\s*=\s*' flatagents/flatmachine.py | grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' | tr -d '"')

echo "Python SDK versions:"
echo "  flatagent.py:   $SDK_FLATAGENT_VERSION"
echo "  flatmachine.py: $SDK_FLATMACHINE_VERSION"
echo ""

# Validate versions match
FAILED=0

if [[ "$SDK_FLATAGENT_VERSION" != "$FLATAGENT_VERSION" ]]; then
    echo "  ✗ flatagent.py version ($SDK_FLATAGENT_VERSION) != spec version ($FLATAGENT_VERSION)"
    FAILED=1
else
    echo "  ✓ flatagent.py matches spec ($FLATAGENT_VERSION)"
fi

if [[ "$SDK_FLATMACHINE_VERSION" != "$FLATMACHINE_VERSION" ]]; then
    echo "  ✗ flatmachine.py version ($SDK_FLATMACHINE_VERSION) != spec version ($FLATMACHINE_VERSION)"
    FAILED=1
else
    echo "  ✓ flatmachine.py matches spec ($FLATMACHINE_VERSION)"
fi

if [[ "$FAILED" -eq 1 ]]; then
    echo ""
    echo "RELEASE ABORTED: SDK version mismatch with TypeScript specs."
    echo "Update SPEC_VERSION in flatagent.py and/or flatmachine.py to match."
    exit 1
fi

echo ""

# Generate spec assets from root specs
echo "Generating spec assets..."
"$REPO_ROOT/scripts/generate-spec-assets.sh" "$ASSETS_DIR"
echo ""

# Verify generated assets match root specs
echo "Verifying spec assets..."
FAILED=0

for file in flatagent.d.ts flatmachine.d.ts; do
    if [ ! -f "$ASSETS_DIR/$file" ]; then
        echo "  ✗ $file (missing)"
        FAILED=1
    elif ! diff -q "$REPO_ROOT/$file" "$ASSETS_DIR/$file" > /dev/null 2>&1; then
        echo "  ✗ $file (does not match root)"
        FAILED=1
    else
        echo "  ✓ $file"
    fi
done

for file in flatagent.slim.d.ts flatmachine.slim.d.ts \
            flatagent.schema.json flatmachine.schema.json; do
    if [ ! -f "$ASSETS_DIR/$file" ]; then
        echo "  ✗ $file (missing)"
        FAILED=1
    else
        echo "  ✓ $file"
    fi
done

if [ "$FAILED" -eq 1 ]; then
    echo ""
    echo "RELEASE ABORTED: Spec asset generation failed."
    exit 1
fi
echo "All spec assets verified."
echo ""

# Setup virtualenv with build tools
if [ ! -d ~/virtualenvs/twine ]; then
    python -m venv ~/virtualenvs/twine
    ~/virtualenvs/twine/bin/pip install --upgrade build twine
fi
source ~/virtualenvs/twine/bin/activate

# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build
python -m build

# Upload to PyPI
twine upload dist/*

echo "Released $(ls dist/*.whl | head -1 | xargs basename)"
