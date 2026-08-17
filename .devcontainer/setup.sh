#!/bin/bash

echo "Setting up development environment..."

# Install Node.js (LTS)
echo "🟢 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install nodejs -y

# Install pnpm
echo "📦 Installing pnpm package manager..."
sudo npm install -g pnpm

# uv installs every Python dependency below, in place of pip. Bootstrapped with
# pip because pip is what the devcontainer Python image ships; nothing else here
# uses it.
#
# The pin is inline, which is not where the rest of Jartan keeps it. Elsewhere
# uv's version sits on one line of ci/requirements.txt, read by CI's setup-uv
# via `version-file:` and bumped by Dependabot's "/ci" entry. This repository
# has neither — no .github/workflows/ and no .github/dependabot.yml — so that
# file would exist only to hold this line, with no gate reading it and nothing
# watching it. It moves to ci/requirements.txt the day this repository gets CI
# (JAR-287). Until then this pin and the Dockerfile's uv-bin tag are bumped by
# hand, together.
UV_VERSION=0.12.5
echo "🐍 Installing uv ${UV_VERSION}..."
pip install "uv==${UV_VERSION}" || echo "Warning: uv install failed" >&2

# --system: the container is the isolation, so packages go to its interpreter
# rather than a venv. uv refuses a non-venv target without this.
echo "Installing Python dependencies..."
while IFS= read -r -d '' req_file; do
    echo "   Installing from $req_file..."
    uv pip install --system -r "$req_file"
done < <(find . -name "requirements.txt" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/.tox/*" -type f -print0 2>/dev/null)

# Install Python dependencies from pyproject.toml files (editable installs).
# The venv/tox paths are pruned here and above because README's setup creates a
# project-local ./.venv, and some wheels ship their own pyproject.toml or
# requirements.txt into site-packages — without the prune a rebuilt container
# would try to install every one of them.
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