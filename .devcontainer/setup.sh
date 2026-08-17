#!/bin/bash

echo "Setting up development environment..."

# Node.js and pnpm come from the node devcontainer feature (see
# devcontainer.json), which installs both by default — nothing to do here.

# Pinned inline: no CI and no Dependabot here, so a ci/requirements.txt would
# have nothing reading or bumping it. Keep in step with the Dockerfile's uv tag.
UV_VERSION=0.12.5
echo "🐍 Installing uv ${UV_VERSION}..."
pip install "uv==${UV_VERSION}" || echo "Warning: uv install failed" >&2

echo "Installing Python dependencies..."
while IFS= read -r -d '' req_file; do
    echo "   Installing from $req_file..."
    uv pip install --system -r "$req_file"
done < <(find . -name "requirements.txt" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/.tox/*" -type f -print0 2>/dev/null)

# Install Python dependencies from pyproject.toml files (editable installs)
echo "Installing Python packages from pyproject.toml..."
while IFS= read -r -d '' pyproject_file; do
    dir=$(dirname "$pyproject_file")
    echo "   Installing from $dir..."
    uv pip install --system -e "$dir"
done < <(find . -name "pyproject.toml" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/.tox/*" -type f -print0 2>/dev/null)

echo "Development environment setup complete!"