#!/bin/bash
# Lint spec_version references against .d.ts SPEC_VERSION constants
# Usage: lint-spec-versions.sh [repo-root]
# Exit: 0 if all versions match, 1 if mismatches found

set -e

# Get the repo root - script can be run from anywhere
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-.}"

# If relative path, make it relative to script location
if [[ ! "$REPO_ROOT" = /* ]]; then
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)/$REPO_ROOT"
fi

FLATAGENT_SPEC="$REPO_ROOT/flatagent.d.ts"
FLATMACHINE_SPEC="$REPO_ROOT/flatmachine.d.ts"
EXTRACTOR="$SCRIPT_DIR/generate-spec-assets.ts"

# Verify spec files exist
if [[ ! -f "$FLATAGENT_SPEC" ]]; then
    echo "Error: flatagent.d.ts not found at $FLATAGENT_SPEC"
    exit 1
fi

if [[ ! -f "$FLATMACHINE_SPEC" ]]; then
    echo "Error: flatmachine.d.ts not found at $FLATMACHINE_SPEC"
    exit 1
fi

# Extract spec versions using the TypeScript extractor
echo "Extracting spec versions from SPEC_VERSION constants..."
FLATAGENT_VERSION=$(cd "$SCRIPT_DIR" && npx tsx generate-spec-assets.ts --extract-version "$FLATAGENT_SPEC")
FLATMACHINE_VERSION=$(cd "$SCRIPT_DIR" && npx tsx generate-spec-assets.ts --extract-version "$FLATMACHINE_SPEC")

if [[ -z "$FLATAGENT_VERSION" || -z "$FLATMACHINE_VERSION" ]]; then
    echo "Error: Could not extract spec versions"
    exit 1
fi

echo "Source of truth:"
echo "  flatagent.d.ts:   $FLATAGENT_VERSION"
echo "  flatmachine.d.ts: $FLATMACHINE_VERSION"
echo ""

# Find all YAML/JSON files with spec_version
cd "$REPO_ROOT"

FLATAGENT_MISMATCHES=()
FLATMACHINE_MISMATCHES=()

while IFS= read -r file; do
    # Extract spec and spec_version from the file
    SPEC=$(rg '^spec:\s*(\w+)' "$file" -o -r '$1' --no-heading | head -1)
    VERSION=$(rg 'spec_version.*([0-9]+\.[0-9]+\.[0-9]+)' "$file" -o -r '$1' --no-heading | head -1)

    if [[ -z "$VERSION" ]]; then
        continue
    fi

    # Check against appropriate spec version
    if [[ "$SPEC" == "flatagent" ]]; then
        if [[ "$VERSION" != "$FLATAGENT_VERSION" ]]; then
            FLATAGENT_MISMATCHES+=("$file: $VERSION (should be $FLATAGENT_VERSION)")
        fi
    elif [[ "$SPEC" == "flatmachine" ]]; then
        if [[ "$VERSION" != "$FLATMACHINE_VERSION" ]]; then
            FLATMACHINE_MISMATCHES+=("$file: $VERSION (should be $FLATMACHINE_VERSION)")
        fi
    fi
done < <(rg 'spec_version' --type yaml --type json -l)

# Report results
TOTAL_MISMATCHES=$((${#FLATAGENT_MISMATCHES[@]} + ${#FLATMACHINE_MISMATCHES[@]}))

if [[ $TOTAL_MISMATCHES -gt 0 ]]; then
    echo "❌ Found $TOTAL_MISMATCHES file(s) with mismatched spec_version:"
    echo ""
    
    if [[ ${#FLATAGENT_MISMATCHES[@]} -gt 0 ]]; then
        echo "FlatAgent mismatches:"
        for mismatch in "${FLATAGENT_MISMATCHES[@]}"; do
            echo "  - $mismatch"
        done
        echo ""
    fi
    
    if [[ ${#FLATMACHINE_MISMATCHES[@]} -gt 0 ]]; then
        echo "FlatMachine mismatches:"
        for mismatch in "${FLATMACHINE_MISMATCHES[@]}"; do
            echo "  - $mismatch"
        done
        echo ""
    fi
    
    exit 1
else
    echo "✓ All spec_version references match:"
    echo "  - flatagent configs use v$FLATAGENT_VERSION"
    echo "  - flatmachine configs use v$FLATMACHINE_VERSION"
    exit 0
fi
