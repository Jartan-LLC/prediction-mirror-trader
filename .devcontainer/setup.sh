#!/bin/bash

echo "Setting up development environment..."

# Install Node.js (LTS)
echo "🟢 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install nodejs -y

# Install pnpm
echo "📦 Installing pnpm package manager..."
sudo npm install -g pnpm

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

# Install Claude Code plugins (fallback for fresh Docker volumes)
if command -v claude &> /dev/null; then
    if ! claude plugin list 2>/dev/null | grep -q everything-claude-code; then
        echo "Installing everything-claude-code plugin..."
        claude plugin marketplace add affaan-m/everything-claude-code 2>/dev/null || true
        claude plugin install everything-claude-code@everything-claude-code --scope project 2>/dev/null || true
    else
        echo "everything-claude-code plugin already installed."
    fi
else
    echo "Claude Code CLI not found, skipping plugin installation."
fi

echo "Development environment setup complete!"