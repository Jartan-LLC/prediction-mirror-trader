#!/bin/bash

echo "Setting up development environment..."

# Install Node.js (LTS)
echo "🟢 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install nodejs -y

# Install pnpm
echo "📦 Installing pnpm package manager..."
sudo npm install -g pnpm

# Install Python dependencies from all requirements.txt files
echo "Installing Python dependencies..."
while IFS= read -r -d '' req_file; do
    echo "   Installing from $req_file..."
    pip install -r "$req_file"
done < <(find . -name "requirements.txt" -type f -print0 2>/dev/null)

# Install Python dependencies from pyproject.toml files (editable installs)
echo "Installing Python packages from pyproject.toml..."
while IFS= read -r -d '' pyproject_file; do
    dir=$(dirname "$pyproject_file")
    echo "   Installing from $dir..."
    pip install -e "$dir"
done < <(find . -name "pyproject.toml" -type f -print0 2>/dev/null)

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