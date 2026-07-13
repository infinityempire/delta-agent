#!/bin/bash
# Setup script for zeta-agent repository

set -e

echo "==============================================="
echo "  Zeta Agent - Repository Setup"
echo "==============================================="

# Navigate to script directory
cd "$(dirname "$0")"

# Check if git remote exists
if git remote get-url origin &>/dev/null; then
    echo "Remote already configured"
else
    echo ""
    echo "Creating GitHub repository..."
    
    # Try gh CLI first
    if gh repo create zeta-agent --public --description "Zeta - Multi-Agent Reddit Marketing & Distribution System" 2>/dev/null; then
        echo "Repository created with gh CLI"
        git remote add origin https://github.com/infinityempire/zeta-agent.git
    else
        echo ""
        echo "Could not create repository automatically."
        echo ""
        echo "Please create manually:"
        echo "  1. Go to: https://github.com/new"
        echo "  2. Name: zeta-agent"
        echo "  3. Select: Public"
        echo "  4. Click: Create repository"
        echo ""
        echo "Then run:"
        echo "  git remote add origin https://github.com/infinityempire/zeta-agent.git"
        echo "  ./setup_repo.sh"
        exit 1
    fi
fi

echo ""
echo "Pushing to remote..."
git branch -M main
git push -u origin main

echo ""
echo "==============================================="
echo "  Setup Complete!"
echo "Repository: https://github.com/infinityempire/zeta-agent"
echo "==============================================="
